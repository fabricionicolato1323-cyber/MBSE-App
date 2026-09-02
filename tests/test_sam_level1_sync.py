from __future__ import annotations

import unittest

from sam_connection import SamSettings
from sam_level1_sync import (
    SamLevel1SyncError,
    build_level1_sync_plan,
    level1_snapshot_digest,
    sync_level1_to_sam,
)


class FakeElement:
    counter = 0

    def __init__(self, element_type: str, **kwargs):
        type(self).counter += 1
        self.id = f"fake-{type(self).counter}"
        self.element_type = element_type
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeProject:
    def __init__(self):
        self.root = FakeElement("Package", name="Root")
        self.elements = [self.root]
        self.transaction_started = 0
        self.transaction_stopped = 0

    def get_root_package(self):
        return self.root

    def find_elements_by_name(self, name):
        return [element for element in self.elements if getattr(element, "name", None) == name]

    def start_transactional_mode(self):
        self.transaction_started += 1

    def stop_transactional_mode(self):
        self.transaction_stopped += 1


class FakeConnector:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeProjectManager:
    project = FakeProject()

    def __init__(self, connector):
        self.connector = connector

    def get_scripting_project(self, project_id):
        self.project_id = project_id
        return type(self).project


class FakeFactory:
    def __init__(self, project, connector):
        self.project = project
        self.connector = connector

    def __getattr__(self, name):
        if not name.startswith("create_"):
            raise AttributeError(name)
        element_type = "".join(part.capitalize() for part in name[len("create_"):].split("_"))

        def create(**kwargs):
            element = FakeElement(element_type, **kwargs)
            self.project.elements.append(element)
            return element

        return create


class SamLevel1SyncTests(unittest.TestCase):
    def setUp(self):
        FakeElement.counter = 0
        FakeProjectManager.project = FakeProject()
        self.settings = SamSettings(
            server_url="https://sam.example.test",
            organization_id="org-1",
            project_id="project-1",
            access_token="secret",
            use_ssl=True,
        )
        self.model = {
            "graph": {"model_name": "Threat protection"},
            "nodes": [
                {"id": "cap", "type": "OperationalCapability", "name": "Keep area safe"},
                {"id": "entity", "type": "OperationalEntity", "name": "Control Center"},
                {"id": "building", "type": "OperationalEntity", "name": "Building"},
                {"id": "actor", "type": "OperationalActor", "name": "Operator"},
                {
                    "id": "detect",
                    "type": "OperationalActivity",
                    "name": "Detect threat",
                    "characteristics": [
                        {"name": "Latency", "value_type": "number", "value": 2, "unit": "s"}
                    ],
                },
                {"id": "assess", "type": "OperationalActivity", "name": "Assess threat"},
            ],
            "edges": [
                {"source": "entity", "target": "actor", "type": "CONTAINS"},
                {"source": "actor", "target": "detect", "type": "PERFORMS"},
                {"source": "entity", "target": "assess", "type": "PERFORMS"},
                {
                    "source": "detect",
                    "target": "assess",
                    "type": "OPERATIONAL_EXCHANGE",
                    "name": "Threat information",
                },
                {
                    "source": "actor",
                    "target": "entity",
                    "type": "COMMUNICATION_MEAN",
                    "name": "Radio",
                },
                {"source": "detect", "target": "cap", "type": "SUPPORTS_CAPABILITY"},
                {"source": "actor", "target": "building", "type": "LOCATED_IN"},
            ],
        }
        self.scenarios = [
            {
                "id": "scenario-1",
                "name": "Detection scenario",
                "valid": True,
                "steps": [
                    {"kind": "activity", "activity_id": "detect"},
                    {
                        "kind": "interaction",
                        "exchange_name": "Threat information",
                    },
                    {"kind": "activity", "activity_id": "assess"},
                ],
            }
        ]

    def test_plan_is_stable_and_reports_native_strategies(self):
        first = build_level1_sync_plan(
            self.model,
            scenarios=self.scenarios,
            project_id="project-1",
        )
        reordered = {
            **self.model,
            "nodes": list(reversed(self.model["nodes"])),
            "edges": list(reversed(self.model["edges"])),
        }
        second = build_level1_sync_plan(
            reordered,
            scenarios=list(reversed(self.scenarios)),
            project_id="project-1",
        )
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first["snapshot_digest"], second["snapshot_digest"])
        self.assertEqual(first["snapshot_digest"], level1_snapshot_digest(self.model, self.scenarios))
        self.assertEqual(first["counts"]["elements"], 6)
        self.assertEqual(first["counts"]["relationships"], 7)
        self.assertEqual(first["counts"]["scenarios"], 1)
        self.assertEqual(first["counts"]["relationship_strategies"]["perform"], 2)
        self.assertFalse(first["sam_write_performed"])

    def test_unknown_semantics_block_transfer_before_any_sam_write(self):
        model = {
            "nodes": [{"id": "x", "type": "UnknownType", "name": "Unknown"}],
            "edges": [],
        }
        plan = build_level1_sync_plan(model, project_id="project-1")
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(len(plan["unsupported_nodes"]), 1)
        with self.assertRaises(SamLevel1SyncError):
            sync_level1_to_sam(
                model,
                scenarios=[],
                settings=self.settings,
                connector_class=FakeConnector,
                project_manager_class=FakeProjectManager,
                factory_class=FakeFactory,
            )
        self.assertEqual(FakeProjectManager.project.transaction_started, 0)

    def test_digest_mismatch_blocks_write(self):
        with self.assertRaises(SamLevel1SyncError):
            sync_level1_to_sam(
                self.model,
                scenarios=self.scenarios,
                settings=self.settings,
                expected_digest="old-review",
                connector_class=FakeConnector,
                project_manager_class=FakeProjectManager,
                factory_class=FakeFactory,
            )
        self.assertEqual(FakeProjectManager.project.transaction_started, 0)

    def test_sync_creates_one_transactional_snapshot_with_native_semantics(self):
        digest = level1_snapshot_digest(self.model, self.scenarios)
        result = sync_level1_to_sam(
            self.model,
            scenarios=self.scenarios,
            settings=self.settings,
            expected_digest=digest,
            connector_class=FakeConnector,
            project_manager_class=FakeProjectManager,
            factory_class=FakeFactory,
        )
        project = FakeProjectManager.project
        self.assertEqual(result["status"], "synced")
        self.assertTrue(result["sam_write_performed"])
        self.assertEqual(project.transaction_started, 1)
        self.assertEqual(project.transaction_stopped, 1)
        self.assertEqual(result["created"]["source_elements"], 6)
        self.assertEqual(result["created"]["native_relationships"], 6)
        self.assertEqual(result["created"]["characteristic_attributes"], 1)
        self.assertEqual(result["created"]["scenarios"], 1)
        created_types = {element.element_type for element in project.elements}
        self.assertIn("RequirementUsage", created_types)
        self.assertIn("PartUsage", created_types)
        self.assertIn("ActionUsage", created_types)
        self.assertIn("PerformActionUsage", created_types)
        self.assertIn("FlowConnectionUsage", created_types)
        self.assertIn("ConnectionUsage", created_types)
        self.assertIn("AllocationUsage", created_types)
        self.assertIn("ReferenceUsage", created_types)
        self.assertIn("Succession", created_types)
        self.assertIn("TextualRepresentation", created_types)

    def test_resending_same_snapshot_is_idempotent(self):
        digest = level1_snapshot_digest(self.model, self.scenarios)
        first = sync_level1_to_sam(
            self.model,
            scenarios=self.scenarios,
            settings=self.settings,
            expected_digest=digest,
            connector_class=FakeConnector,
            project_manager_class=FakeProjectManager,
            factory_class=FakeFactory,
        )
        second = sync_level1_to_sam(
            self.model,
            scenarios=self.scenarios,
            settings=self.settings,
            expected_digest=digest,
            connector_class=FakeConnector,
            project_manager_class=FakeProjectManager,
            factory_class=FakeFactory,
        )
        self.assertEqual(first["status"], "synced")
        self.assertEqual(second["status"], "already_synced")
        self.assertFalse(second["sam_write_performed"])
        self.assertEqual(FakeProjectManager.project.transaction_started, 1)
        self.assertEqual(FakeProjectManager.project.transaction_stopped, 1)


if __name__ == "__main__":
    unittest.main()
