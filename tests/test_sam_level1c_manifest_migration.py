from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from sam_connection import SamSettings
from sam_level1_incremental import (
    SYNC_STATE_VERSION,
    _edge_fingerprint,
    _scenario_fingerprint,
    build_incremental_plan,
    migrate_legacy_relationship_state,
)
from sam_level1_sync import SamLevel1SyncError, level1_snapshot_digest


class FakeElement:
    def __init__(self, element_id: str, name: str, owner=None):
        self.id = element_id
        self.name = name
        self.owner = owner


class FakeProject:
    def __init__(self, elements):
        self.elements = list(elements)

    def find_element_by_id(self, element_id):
        return next((item for item in self.elements if item.id == element_id), None)

    def find_elements_by_name(self, name):
        return [item for item in self.elements if item.name == name]


class Level1CManifestMigrationTests(unittest.TestCase):
    def setUp(self):
        self.settings = SamSettings(
            server_url="https://sam.example",
            organization_id="org",
            project_id="project-1",
            access_token="token",
            use_ssl=True,
        )
        self.baseline = {
            "directed": True,
            "multigraph": True,
            "graph": {"model_name": "Migration Test"},
            "nodes": [
                {"id": "activity-1", "type": "OperationalActivity", "name": "Detect threat"},
                {"id": "activity-2", "type": "OperationalActivity", "name": "Report threat"},
            ],
            "edges": [
                {
                    "source": "activity-1",
                    "target": "activity-2",
                    "key": 0,
                    "type": "OPERATIONAL_EXCHANGE",
                    "name": "Threat location",
                }
            ],
        }
        package = FakeElement("pkg-1", "MBSE_Instance_Migration_Test_deadbeef")
        behavior = FakeElement("behavior-1", "oa_operationalBehavior", package)
        exchange = FakeElement("rel-1", "Threat location", behavior)
        self.project = FakeProject([package, behavior, exchange])
        self.state = {
            "version": 1,
            "project_id": self.settings.project_id,
            "library_package_name": "MBSE_ArcadiaOA_Library_v1",
            "instance_package_name": package.name,
            "instance_package_id": package.id,
            "snapshot_digest": level1_snapshot_digest(self.baseline, []),
            "nodes": {
                "activity-1": {
                    "sam_id": "sam-activity-1",
                    "type": "OperationalActivity",
                    "name": "Detect threat",
                    "source": copy.deepcopy(self.baseline["nodes"][0]),
                },
                "activity-2": {
                    "sam_id": "sam-activity-2",
                    "type": "OperationalActivity",
                    "name": "Report threat",
                    "source": copy.deepcopy(self.baseline["nodes"][1]),
                },
            },
            "edges_fingerprint": _edge_fingerprint(self.baseline),
            "scenarios_fingerprint": _scenario_fingerprint([]),
        }

    def _migrate(self, model):
        with patch(
            "sam_level1_incremental._load_project",
            return_value=(object(), object(), self.project, object),
        ):
            return migrate_legacy_relationship_state(
                model,
                scenarios=[],
                state=self.state,
                settings=self.settings,
            )

    def test_unchanged_v1_manifest_is_mapped_read_only_to_v2(self):
        migrated = self._migrate(self.baseline)
        self.assertEqual(migrated["version"], SYNC_STATE_VERSION)
        self.assertEqual(len(migrated["relationships"]), 1)
        record = next(iter(migrated["relationships"].values()))
        self.assertEqual(record["sam_id"], "rel-1")
        self.assertEqual(record["name"], "Threat location")
        self.assertEqual(migrated["snapshot_digest"], self.state["snapshot_digest"])

    def test_additive_kill_count_is_proven_and_becomes_create(self):
        changed = copy.deepcopy(self.baseline)
        changed["edges"].append(
            {
                "source": "activity-2",
                "target": "activity-1",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Kill count",
            }
        )
        migrated = self._migrate(changed)
        working = copy.deepcopy(changed)
        working["graph"]["sam_sync"] = migrated
        plan = build_incremental_plan(working, scenarios=[], settings=self.settings)

        self.assertTrue(plan["supported"])
        self.assertEqual(plan["relationship_counts"]["create"], 1)
        self.assertEqual(plan["relationship_creates"][0]["edge"]["name"], "Kill count")
        self.assertEqual(plan["relationship_counts"]["delete"], 0)

    def test_legacy_relationship_rename_is_not_guessed(self):
        changed = copy.deepcopy(self.baseline)
        changed["edges"][0]["name"] = "Renamed threat location"
        with self.assertRaisesRegex(SamLevel1SyncError, "provably additive"):
            self._migrate(changed)


if __name__ == "__main__":
    unittest.main()
