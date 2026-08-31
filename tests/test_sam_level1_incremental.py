from __future__ import annotations

import copy
import unittest

from sam_connection import SamSettings
from sam_level1_incremental import (
    _edge_fingerprint,
    _edge_identity,
    _other_edge_fingerprint,
    _scenario_fingerprint,
    build_incremental_plan,
)
from sam_level1_sync import level1_snapshot_digest


class SamLevel1IncrementalPlanTests(unittest.TestCase):
    def setUp(self):
        self.settings = SamSettings(
            server_url="https://sam.example",
            organization_id="org",
            project_id="project-1",
            access_token="token",
            use_ssl=True,
        )
        self.model = {
            "directed": True,
            "multigraph": True,
            "graph": {"model_name": "Incremental Test"},
            "nodes": [
                {"id": "entity-1", "type": "OperationalEntity", "name": "Vehicle"},
                {"id": "activity-1", "type": "OperationalActivity", "name": "Detect threat"},
                {"id": "activity-2", "type": "OperationalActivity", "name": "Engage threat"},
            ],
            "edges": [
                {
                    "source": "entity-1",
                    "target": "activity-1",
                    "key": 0,
                    "type": "PERFORMS",
                    "name": "performs",
                }
            ],
        }
        self.state = self.state_for(self.model)

    def state_for(self, model, *, relationship_sam_ids=None):
        relationship_sam_ids = relationship_sam_ids or {}
        relationships = {}
        for edge in model.get("edges", []):
            if edge.get("type") != "OPERATIONAL_EXCHANGE":
                continue
            identity = _edge_identity(edge)
            relationships[identity] = {
                "sam_id": relationship_sam_ids.get(identity, f"sam-rel-{len(relationships) + 1}"),
                "type": "OPERATIONAL_EXCHANGE",
                "source_id": edge["source"],
                "target_id": edge["target"],
                "key": edge.get("key", 0),
                "name": edge.get("name") or "OPERATIONAL_EXCHANGE",
                "source": copy.deepcopy(edge),
            }
        return {
            "version": 2,
            "project_id": "project-1",
            "library_package_name": "MBSE_ArcadiaOA_Library_v1",
            "instance_package_name": "MBSE_Instance_Incremental_Test_deadbeef",
            "instance_package_id": "pkg-1",
            "snapshot_digest": level1_snapshot_digest(model, []),
            "nodes": {
                node["id"]: {
                    "sam_id": f"sam-{node['id']}",
                    "type": node["type"],
                    "name": node["name"],
                    "source": copy.deepcopy(node),
                }
                for node in model["nodes"]
            },
            "relationships": relationships,
            "relationship_tracking_complete": True,
            "other_edges_fingerprint": _other_edge_fingerprint(model),
            "edges_fingerprint": _edge_fingerprint(model),
            "scenarios_fingerprint": _scenario_fingerprint([]),
        }

    def with_state(self, model, state=None):
        value = copy.deepcopy(model)
        value.setdefault("graph", {})["sam_sync"] = copy.deepcopy(state or self.state)
        return value

    def test_unchanged_model_is_noop(self):
        plan = build_incremental_plan(
            self.with_state(self.model), scenarios=[], settings=self.settings
        )
        self.assertEqual(plan["mode"], "incremental_noop")
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["counts"]["update"], 0)
        self.assertEqual(plan["relationship_counts"]["create"], 0)

    def test_name_only_change_is_one_update(self):
        changed = copy.deepcopy(self.model)
        changed["nodes"][1]["name"] = "Detect incoming threat"
        plan = build_incremental_plan(
            self.with_state(changed), scenarios=[], settings=self.settings
        )
        self.assertEqual(plan["mode"], "incremental_change_set")
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["counts"]["update"], 1)
        self.assertEqual(plan["updates"][0]["new_name"], "Detect incoming threat")

    def test_isolated_new_element_is_a_supported_create(self):
        changed = copy.deepcopy(self.model)
        changed["nodes"].append(
            {"id": "capability-2", "type": "OperationalCapability", "name": "Track threat"}
        )
        plan = build_incremental_plan(
            self.with_state(changed), scenarios=[], settings=self.settings
        )
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["counts"]["create"], 1)
        self.assertEqual(plan["unsupported_changes"], [])

    def test_isolated_removed_element_is_a_supported_delete(self):
        baseline = copy.deepcopy(self.model)
        baseline["nodes"].append(
            {"id": "capability-2", "type": "OperationalCapability", "name": "Track threat"}
        )
        state = self.state_for(baseline)
        changed = copy.deepcopy(baseline)
        changed["nodes"] = [
            node for node in changed["nodes"] if node["id"] != "capability-2"
        ]
        plan = build_incremental_plan(
            self.with_state(changed, state), scenarios=[], settings=self.settings
        )
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["counts"]["delete"], 1)
        self.assertEqual(plan["deletes"][0]["source_id"], "capability-2")

    def test_operational_exchange_create_is_supported(self):
        changed = copy.deepcopy(self.model)
        changed["edges"].append(
            {
                "source": "activity-1",
                "target": "activity-2",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Kill count",
            }
        )
        plan = build_incremental_plan(
            self.with_state(changed), scenarios=[], settings=self.settings
        )
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["relationship_counts"]["create"], 1)
        self.assertEqual(plan["relationship_creates"][0]["edge"]["name"], "Kill count")
        self.assertFalse(plan["relationship_changes_pending"])

    def test_operational_exchange_rename_is_replace_update(self):
        baseline = copy.deepcopy(self.model)
        baseline["edges"].append(
            {
                "source": "activity-1",
                "target": "activity-2",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Kill count",
            }
        )
        state = self.state_for(baseline)
        changed = copy.deepcopy(baseline)
        changed["edges"][-1]["name"] = "Ammunition count"
        plan = build_incremental_plan(
            self.with_state(changed, state), scenarios=[], settings=self.settings
        )
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["relationship_counts"]["update"], 1)
        self.assertEqual(plan["relationship_updates"][0]["new_name"], "Ammunition count")

    def test_operational_exchange_delete_is_supported(self):
        baseline = copy.deepcopy(self.model)
        baseline["edges"].append(
            {
                "source": "activity-1",
                "target": "activity-2",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Kill count",
            }
        )
        state = self.state_for(baseline)
        changed = copy.deepcopy(baseline)
        changed["edges"].pop()
        plan = build_incremental_plan(
            self.with_state(changed, state), scenarios=[], settings=self.settings
        )
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["relationship_counts"]["delete"], 1)
        self.assertTrue(plan["relationship_deletes"][0]["sam_id"])

    def test_new_performs_relationship_still_blocks_level1c_increment2(self):
        changed = copy.deepcopy(self.model)
        changed["edges"].append(
            {
                "source": "entity-1",
                "target": "activity-2",
                "key": 0,
                "type": "PERFORMS",
                "name": "performs",
            }
        )
        plan = build_incremental_plan(
            self.with_state(changed), scenarios=[], settings=self.settings
        )
        self.assertFalse(plan["supported"])
        self.assertTrue(plan["relationship_changes_pending"])
        self.assertTrue(
            any("outside OPERATIONAL_EXCHANGE" in item for item in plan["unsupported_changes"])
        )

    def test_legacy_v1_relationship_delta_requires_runner_migration(self):
        legacy = copy.deepcopy(self.state)
        legacy["version"] = 1
        legacy.pop("relationships", None)
        legacy.pop("other_edges_fingerprint", None)
        changed = copy.deepcopy(self.model)
        changed["edges"].append(
            {
                "source": "activity-1",
                "target": "activity-2",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Kill count",
            }
        )
        plan = build_incremental_plan(
            self.with_state(changed, legacy), scenarios=[], settings=self.settings
        )
        self.assertFalse(plan["supported"])
        self.assertTrue(any("v1-to-v2 migration" in x for x in plan["unsupported_changes"]))

    def test_scenario_change_blocks_entire_write(self):
        scenario = {
            "id": "scenario-1",
            "name": "Nominal",
            "valid": True,
            "steps": [{"kind": "activity", "activity_id": "activity-1"}],
        }
        plan = build_incremental_plan(
            self.with_state(self.model), scenarios=[scenario], settings=self.settings
        )
        self.assertFalse(plan["supported"])
        self.assertTrue(plan["scenario_changes_pending"])


if __name__ == "__main__":
    unittest.main()
