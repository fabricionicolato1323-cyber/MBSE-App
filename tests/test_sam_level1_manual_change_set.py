from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import sam_level1_incremental_runner as runner
from sam_connection import SamSettings
from sam_level1_incremental import _edge_fingerprint, _scenario_fingerprint
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

    def _manifest(self):
        node = copy.deepcopy(self.model["nodes"][0])
        return {
            "version": 1,
            "project_id": self.settings.project_id,
            "library_package_name": "MBSE_ArcadiaOA_Library_v1",
            "instance_package_name": "MBSE_Instance_Manual_Sync_Test_deadbeef",
            "instance_package_id": "pkg-1",
            "snapshot_digest": level1_snapshot_digest(self.model, []),
            "nodes": {
                "cap-1": {
                    "sam_id": "sam-cap-1",
                    "type": "OperationalCapability",
                    "name": "Protect area",
                    "source": node,
                }
            },
            "edges_fingerprint": _edge_fingerprint(self.model),
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

    def test_relationship_delta_is_visible_and_blocks_partial_sync(self):
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


if __name__ == "__main__":
    unittest.main()
