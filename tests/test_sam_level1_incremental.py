from __future__ import annotations

import copy
import unittest

from sam_connection import SamSettings
from sam_level1_incremental import build_incremental_plan
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
        digest = level1_snapshot_digest(self.model, [])
        self.state = {
            "version": 1,
            "project_id": "project-1",
            "library_package_name": "MBSE_ArcadiaOA_Library_v1",
            "instance_package_name": "MBSE_Instance_Incremental_Test_deadbeef",
            "instance_package_id": "pkg-1",
            "snapshot_digest": digest,
            "nodes": {
                "entity-1": {
                    "sam_id": "sam-entity",
                    "type": "OperationalEntity",
                    "name": "Vehicle",
                    "source": copy.deepcopy(self.model["nodes"][0]),
                },
                "activity-1": {
                    "sam_id": "sam-activity",
                    "type": "OperationalActivity",
                    "name": "Detect threat",
                    "source": copy.deepcopy(self.model["nodes"][1]),
                },
            },
        }
        from sam_level1_incremental import _edge_fingerprint, _scenario_fingerprint

        self.state["edges_fingerprint"] = _edge_fingerprint(self.model)
        self.state["scenarios_fingerprint"] = _scenario_fingerprint([])

    def with_state(self, model):
        value = copy.deepcopy(model)
        value.setdefault("graph", {})["sam_sync"] = copy.deepcopy(self.state)
        return value

    def test_unchanged_model_is_noop(self):
        plan = build_incremental_plan(
            self.with_state(self.model), scenarios=[], settings=self.settings
        )
        self.assertEqual(plan["mode"], "incremental_noop")
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["counts"]["update"], 0)

    def test_name_only_change_is_one_update(self):
        changed = copy.deepcopy(self.model)
        changed["nodes"][1]["name"] = "Detect incoming threat"
        plan = build_incremental_plan(
            self.with_state(changed), scenarios=[], settings=self.settings
        )
        self.assertEqual(plan["mode"], "incremental_change_set")
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["counts"]["create"], 0)
        self.assertEqual(plan["counts"]["delete"], 0)
        self.assertEqual(plan["counts"]["update"], 1)
        self.assertEqual(plan["updates"][0]["sam_id"], "sam-activity")
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
        self.assertEqual(plan["creates"][0]["source_id"], "capability-2")
        self.assertEqual(plan["unsupported_changes"], [])

    def test_isolated_removed_element_is_a_supported_delete(self):
        model = copy.deepcopy(self.model)
        model["nodes"].append(
            {"id": "capability-2", "type": "OperationalCapability", "name": "Track threat"}
        )
        state_model = copy.deepcopy(model)
        state = copy.deepcopy(self.state)
        state["nodes"]["capability-2"] = {
            "sam_id": "sam-capability",
            "type": "OperationalCapability",
            "name": "Track threat",
            "source": copy.deepcopy(model["nodes"][2]),
        }
        from sam_level1_incremental import _edge_fingerprint

        state["snapshot_digest"] = level1_snapshot_digest(model, [])
        state["edges_fingerprint"] = _edge_fingerprint(model)
        state_model.setdefault("graph", {})["sam_sync"] = state
        state_model["nodes"] = state_model["nodes"][:2]

        plan = build_incremental_plan(
            state_model, scenarios=[], settings=self.settings
        )
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["counts"]["delete"], 1)
        self.assertEqual(plan["deletes"][0]["sam_id"], "sam-capability")

    def test_new_activity_plus_performs_relationship_blocks_entire_write(self):
        changed = copy.deepcopy(self.model)
        changed["nodes"].append(
            {"id": "activity-2", "type": "OperationalActivity", "name": "Track threat"}
        )
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
        self.assertEqual(plan["counts"]["create"], 1)
        self.assertTrue(plan["relationship_changes_pending"])
        self.assertTrue(
            any("relationship incremental sync is pending" in item for item in plan["unsupported_changes"])
        )

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
