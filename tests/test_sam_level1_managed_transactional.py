from __future__ import annotations

import unittest

from sam_connection import SamSettings
from sam_level1_managed_transactional import (
    SAM_REFERENCE_LIBRARY_PACKAGE,
    ensure_sam_reference_library_transactional,
    sync_level1_to_sam_managed_transactional,
)
from sam_level1_sync import level1_snapshot_digest


class Element:
    counter = 0

    def __init__(self, element_type: str, **kwargs):
        type(self).counter += 1
        self.id = f"element-{type(self).counter}"
        self.element_type = element_type
        for key, value in kwargs.items():
            setattr(self, key, value)


class Project:
    def __init__(self):
        self.root = Element("Package", name="Root")
        self.elements = [self.root]
        self.transaction_starts = 0
        self.transaction_stops = 0

    def get_root_package(self):
        return self.root

    def start_transactional_mode(self):
        self.transaction_starts += 1

    def stop_transactional_mode(self):
        self.transaction_stops += 1

    def find_element_by_id(self, element_id):
        return next((item for item in self.elements if item.id == element_id), None)

    def find_elements_by_name(self, name):
        return [item for item in self.elements if getattr(item, "name", None) == name]


class Connector:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class Manager:
    project = Project()

    def __init__(self, connector):
        self.connector = connector

    def get_scripting_project(self, project_id):
        return type(self).project


class Factory:
    def __init__(self, project, connector):
        self.project = project
        self.connector = connector

    def __getattr__(self, name):
        if not name.startswith("create_"):
            raise AttributeError(name)
        element_type = "".join(part.capitalize() for part in name[7:].split("_"))

        def create(**kwargs):
            element = Element(element_type, **kwargs)
            self.project.elements.append(element)
            return element

        return create


class ManagedTransactionalTests(unittest.TestCase):
    def setUp(self):
        Element.counter = 0
        Manager.project = Project()
        self.settings = SamSettings(
            server_url="https://sam.example.test",
            organization_id="org",
            project_id="project",
            access_token="secret",
            use_ssl=True,
        )
        self.model = {
            "graph": {"model_name": "Fast Baseline"},
            "nodes": [
                {
                    "id": "entity",
                    "type": "OperationalEntity",
                    "name": "Control Center",
                    "characteristics": [
                        {
                            "name": "Response time",
                            "value_type": "number",
                            "value": 5,
                            "unit": "s",
                        }
                    ],
                },
                {"id": "actor", "type": "OperationalActor", "name": "Operator"},
                {"id": "a1", "type": "OperationalActivity", "name": "Observe"},
                {"id": "a2", "type": "OperationalActivity", "name": "Authorize"},
                {"id": "cap", "type": "OperationalCapability", "name": "Safe passage"},
            ],
            "edges": [
                {"source": "entity", "target": "actor", "type": "CONTAINS"},
                {"source": "actor", "target": "a1", "type": "PERFORMS"},
                {"source": "entity", "target": "a2", "type": "PERFORMS"},
                {
                    "source": "a1",
                    "target": "a2",
                    "type": "OPERATIONAL_EXCHANGE",
                    "name": "Authorization request",
                },
                {"source": "a1", "target": "cap", "type": "SUPPORTS_CAPABILITY"},
                {
                    "source": "actor",
                    "target": "entity",
                    "type": "COMMUNICATION_MEAN",
                    "name": "Voice",
                },
            ],
        }
        self.scenarios = [
            {
                "id": "scenario",
                "name": "Nominal",
                "valid": True,
                "steps": [
                    {"kind": "activity", "activity_id": "a1"},
                    {"kind": "activity", "activity_id": "a2"},
                ],
            }
        ]

    def kwargs(self):
        return {
            "connector_class": Connector,
            "project_manager_class": Manager,
            "factory_class": Factory,
        }

    def test_reference_library_is_one_transaction_and_reused(self):
        first = ensure_sam_reference_library_transactional(
            self.settings, **self.kwargs()
        )
        second = ensure_sam_reference_library_transactional(
            self.settings, **self.kwargs()
        )

        self.assertEqual(first["status"], "loaded")
        self.assertEqual(first["server_commits"], 1)
        self.assertEqual(second["status"], "already_loaded")
        self.assertEqual(second["server_commits"], 0)
        self.assertEqual(Manager.project.transaction_starts, 1)
        self.assertEqual(Manager.project.transaction_stops, 1)
        self.assertEqual(
            len(Manager.project.find_elements_by_name(SAM_REFERENCE_LIBRARY_PACKAGE)),
            1,
        )

    def test_complete_model_uses_one_transaction_when_library_exists(self):
        ensure_sam_reference_library_transactional(self.settings, **self.kwargs())
        starts_before = Manager.project.transaction_starts
        stops_before = Manager.project.transaction_stops
        digest = level1_snapshot_digest(self.model, self.scenarios)

        result = sync_level1_to_sam_managed_transactional(
            self.model,
            scenarios=self.scenarios,
            settings=self.settings,
            expected_digest=digest,
            **self.kwargs(),
        )

        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["transport"], "transactional_batch")
        self.assertEqual(result["server_commits"], 1)
        self.assertEqual(Manager.project.transaction_starts - starts_before, 1)
        self.assertEqual(Manager.project.transaction_stops - stops_before, 1)
        self.assertEqual(result["created"]["optional_source_annotations"], 0)
        self.assertEqual(result["created"]["characteristic_metadata_comments"], 1)
        self.assertEqual(result["created"]["textual_level1_representation"], 0)

        element_types = [item.element_type for item in Manager.project.elements]
        self.assertNotIn("Documentation", element_types)
        self.assertEqual(element_types.count("Comment"), 1)
        characteristic_comment = next(
            item for item in Manager.project.elements if item.element_type == "Comment"
        )
        self.assertIn("source_characteristic", characteristic_comment.body)
        self.assertIn("Response time", characteristic_comment.body)
        self.assertIn('"value": 5', characteristic_comment.body)
        self.assertIn("FlowConnectionUsage", element_types)
        self.assertIn("ReferenceSubsetting", element_types)

        names = {getattr(item, "name", None) for item in Manager.project.elements}
        self.assertTrue({"Arcadia_OA", "Structure", "Requirements", "Scenarios"}.issubset(names))
        self.assertNotIn("Voice", names)

    def test_second_send_is_idempotent_and_opens_no_new_transaction(self):
        digest = level1_snapshot_digest(self.model, self.scenarios)
        first = sync_level1_to_sam_managed_transactional(
            self.model,
            scenarios=self.scenarios,
            settings=self.settings,
            expected_digest=digest,
            **self.kwargs(),
        )
        starts_before = Manager.project.transaction_starts
        stops_before = Manager.project.transaction_stops

        second = sync_level1_to_sam_managed_transactional(
            self.model,
            scenarios=self.scenarios,
            settings=self.settings,
            expected_digest=digest,
            **self.kwargs(),
        )

        self.assertEqual(first["status"], "synced")
        self.assertEqual(second["status"], "already_synced")
        self.assertEqual(second["server_commits"], 0)
        self.assertEqual(Manager.project.transaction_starts, starts_before)
        self.assertEqual(Manager.project.transaction_stops, stops_before)


if __name__ == "__main__":
    unittest.main()
