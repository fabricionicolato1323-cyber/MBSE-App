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
        # Obtain the stable edge/scenario fingerprints through one initial plan by
        # temporarily using a matching state built from the module's public plan.
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
        self.assertEqual(plan["mode"], "incremental_update")
        self.assertTrue(plan["supported"])
        self.assertEqual(plan["counts"]["create"], 0)
        self.assertEqual(plan["counts"]["delete"], 0)
        self.assertEqual(plan["counts"]["update"], 1)
        self.assertEqual(plan["updates"][0]["sam_id"], "sam-activity")
        self.assertEqual(plan["updates"][0]["new_name"], "Detect incoming threat")

    def test_structural_change_is_blocked_without_rebuild(self):
        changed = copy.deepcopy(self.model)
        changed["nodes"].append(
            {"id": "activity-2", "type": "OperationalActivity", "name": "Track threat"}
        )
        plan = build_incremental_plan(
            self.with_state(changed), scenarios=[], settings=self.settings
        )
        self.assertFalse(plan["supported"])
        self.assertEqual(plan["counts"]["create"], 1)
        self.assertTrue(any("new elements" in item for item in plan["unsupported_changes"]))


if __name__ == "__main__":
    unittest.main()
