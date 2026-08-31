from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import sam_level1_incremental_runner as runner
from sam_connection import SamSettings
from sam_level1_incremental import (
    SYNC_STATE_VERSION,
    _edge_fingerprint,
    _other_edge_fingerprint,
    _scenario_fingerprint,
)
from sam_level1_sync import level1_snapshot_digest


class ManualSamChangeSetPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_root = runner._RUNTIME_ROOT
        runner._RUNTIME_ROOT = Path(self.tempdir.name)
        self.settings = SamSettings(
            server_url="https://sam.example",
            organization_id="org",
            project_id="project-manual",
            access_token="token",
            use_ssl=True,
        )
        self.model = {
            "directed": True,
            "multigraph": True,
            "graph": {"model_name": "Manual Sync Test"},
            "nodes": [
                {"id": "cap-1", "type": "OperationalCapability", "name": "Protect area"},
            ],
            "edges": [],
        }

    def tearDown(self):
        runner._RUNTIME_ROOT = self.previous_root
        self.tempdir.cleanup()

    def _manifest(self, model=None):
        model = copy.deepcopy(model or self.model)
        nodes = {
            str(node["id"]): {
                "sam_id": f"sam-{node['id']}",
                "type": node["type"],
                "name": node["name"],
                "source": copy.deepcopy(node),
            }
            for node in model["nodes"]
        }
        return {
            "version": SYNC_STATE_VERSION,
            "project_id": self.settings.project_id,
            "library_package_name": "MBSE_ArcadiaOA_Library_v1",
            "instance_package_name": "MBSE_Instance_Manual_Sync_Test_deadbeef",
            "instance_package_id": "pkg-1",
            "snapshot_digest": level1_snapshot_digest(model, []),
            "nodes": nodes,
            "relationships": {},
            "relationship_tracking_complete": True,
            "other_edges_fingerprint": _other_edge_fingerprint(model),
            "edges_fingerprint": _edge_fingerprint(model),
            "scenarios_fingerprint": _scenario_fingerprint([]),
        }

    def test_no_manifest_previews_initial_baseline_without_writing(self):
        preview = runner.preview_level1_with_incremental_state(
            self.model,
            scenarios=[],
            settings=self.settings,
        )
        self.assertEqual(preview["sync_status"], "never_synchronized")
        self.assertEqual(preview["delta"]["create"], 1)
        self.assertEqual(preview["library"]["action"], "create_or_reuse")
        self.assertEqual(preview["instance"]["action"], "create_or_adopt")

    def test_manifest_noop_is_reported_as_up_to_date(self):
        runner._save_manifest(self.model, self.settings, self._manifest())
        preview = runner.preview_level1_with_incremental_state(
            self.model,
            scenarios=[],
            settings=self.settings,
        )
        self.assertEqual(preview["sync_status"], "up_to_date")
        self.assertEqual(preview["delta"]["unchanged"], 1)
        self.assertEqual(preview["relationship_delta"]["unchanged"], 0)
        self.assertEqual(preview["library"]["action"], "reuse")
        self.assertEqual(preview["instance"]["action"], "reuse")

    def test_name_change_previews_one_update_and_no_write_side_effect(self):
        runner._save_manifest(self.model, self.settings, self._manifest())
        changed = copy.deepcopy(self.model)
        changed["nodes"][0]["name"] = "Protect operational area"
        before = runner._load_manifest(self.model, self.settings)
        preview = runner.preview_level1_with_incremental_state(
            changed,
            scenarios=[],
            settings=self.settings,
        )
        after = runner._load_manifest(self.model, self.settings)
        self.assertEqual(preview["sync_status"], "local_changes")
        self.assertEqual(preview["delta"]["update"], 1)
        self.assertEqual(preview["delta"]["create"], 0)
        self.assertEqual(preview["delta"]["delete"], 0)
        self.assertEqual(before, after)

    def test_operational_exchange_create_is_visible_and_supported(self):
        baseline = {
            "directed": True,
            "multigraph": True,
            "graph": {"model_name": "Manual Sync Test"},
            "nodes": [
                {"id": "activity-1", "type": "OperationalActivity", "name": "Report threat engagement"},
                {"id": "activity-2", "type": "OperationalActivity", "name": "Receive engagement report"},
            ],
            "edges": [],
        }
        runner._save_manifest(baseline, self.settings, self._manifest(baseline))
        changed = copy.deepcopy(baseline)
        changed["edges"].append(
            {
                "source": "activity-1",
                "target": "activity-2",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Kill count",
            }
        )
        before = runner._load_manifest(baseline, self.settings)
        preview = runner.preview_level1_with_incremental_state(
            changed,
            scenarios=[],
            settings=self.settings,
        )
        after = runner._load_manifest(baseline, self.settings)

        self.assertEqual(preview["sync_status"], "local_changes")
        self.assertEqual(preview["status"], "ready")
        self.assertTrue(preview["supported"])
        self.assertEqual(preview["relationship_delta"]["create"], 1)
        self.assertEqual(preview["relationship_delta"]["update"], 0)
        self.assertEqual(preview["relationship_delta"]["delete"], 0)
        self.assertEqual(preview["relationship_creates"][0]["edge"]["name"], "Kill count")
        self.assertEqual(before, after)

    def test_non_exchange_relationship_delta_remains_blocked(self):
        runner._save_manifest(self.model, self.settings, self._manifest())
        changed = copy.deepcopy(self.model)
        changed["nodes"].append(
            {
                "id": "activity-1",
                "type": "OperationalActivity",
                "name": "Detect threat",
            }
        )
        changed["edges"].append(
            {
                "source": "activity-1",
                "target": "cap-1",
                "key": 0,
                "type": "SUPPORTS_CAPABILITY",
            }
        )
        preview = runner.preview_level1_with_incremental_state(
            changed,
            scenarios=[],
            settings=self.settings,
        )
        self.assertEqual(preview["sync_status"], "local_changes_blocked")
        self.assertEqual(preview["status"], "blocked")
        self.assertTrue(preview["relationship_delta"]["pending"])
        self.assertEqual(preview["delta"]["create"], 1)
        self.assertTrue(
            any(
                "outside OPERATIONAL_EXCHANGE" in item
                for item in preview["unsupported_changes"]
            )
        )


if __name__ == "__main__":
    unittest.main()
