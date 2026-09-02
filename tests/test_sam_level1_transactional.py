from __future__ import annotations

import unittest

from sam_connection import SamSettings
from sam_level1_transactional import (
    ARCADIA_OA_LIBRARY_PACKAGE,
    ensure_arcadia_oa_library,
    level1_instance_package_name,
    sync_level1_to_sam_transactional,
)
from sam_level1_sync import level1_snapshot_digest


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
        return [item for item in self.elements if getattr(item, "name", None) == name]

    def find_element_by_id(self, element_id):
        return next((item for item in self.elements if item.id == element_id), None)

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


class SamLevel1TransactionalTests(unittest.TestCase):
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
                {"id": "actor", "type": "OperationalActor", "name": "Operator"},
                {"id": "detect", "type": "OperationalActivity", "name": "Detect threat"},
            ],
            "edges": [
                {"source": "entity", "target": "actor", "type": "CONTAINS"},
                {"source": "actor", "target": "detect", "type": "PERFORMS"},
                {"source": "detect", "target": "cap", "type": "SUPPORTS_CAPABILITY"},
                {
                    "source": "actor",
                    "target": "entity",
                    "type": "COMMUNICATION_MEAN",
                    "name": "Radio",
                },
            ],
        }

    def kwargs(self):
        return {
            "connector_class": FakeConnector,
            "project_manager_class": FakeProjectManager,
            "factory_class": FakeFactory,
        }

    def test_library_is_loaded_once_in_its_own_transaction(self):
        first = ensure_arcadia_oa_library(self.settings, **self.kwargs())
        second = ensure_arcadia_oa_library(self.settings, **self.kwargs())
        project = FakeProjectManager.project

        self.assertEqual(first["status"], "loaded")
        self.assertEqual(second["status"], "already_loaded")
        self.assertEqual(project.transaction_started, 1)
        self.assertEqual(project.transaction_stopped, 1)
        libraries = project.find_elements_by_name(ARCADIA_OA_LIBRARY_PACKAGE)
        self.assertEqual(len(libraries), 1)
        self.assertEqual(libraries[0].element_type, "LibraryPackage")

    def test_first_send_is_two_transactions_then_resend_is_idempotent(self):
        digest = level1_snapshot_digest(self.model, [])
        first = sync_level1_to_sam_transactional(
            self.model,
            scenarios=[],
            settings=self.settings,
            expected_digest=digest,
            **self.kwargs(),
        )
        second = sync_level1_to_sam_transactional(
            self.model,
            scenarios=[],
            settings=self.settings,
            expected_digest=digest,
            **self.kwargs(),
        )
        project = FakeProjectManager.project
        instance_name = level1_instance_package_name("Threat protection", digest)

        self.assertEqual(first["status"], "synced")
        self.assertEqual(first["mode"], "transactional_library_then_instantiation")
        self.assertEqual(first["package_name"], instance_name)
        self.assertTrue(first["library"]["loaded"])
        self.assertEqual(second["status"], "already_synced")
        self.assertFalse(second["sam_write_performed"])
        self.assertEqual(project.transaction_started, 2)
        self.assertEqual(project.transaction_stopped, 2)
        self.assertEqual(len(project.find_elements_by_name(ARCADIA_OA_LIBRARY_PACKAGE)), 1)
        self.assertEqual(len(project.find_elements_by_name(instance_name)), 1)
        self.assertNotIn("__INCOMPLETE", instance_name)
        self.assertIn("total_seconds", first["timings"])
        self.assertIn("commit_seconds", first["timings"])

    def test_model_elements_reference_definitions_from_separate_library(self):
        digest = level1_snapshot_digest(self.model, [])
        sync_level1_to_sam_transactional(
            self.model,
            scenarios=[],
            settings=self.settings,
            expected_digest=digest,
            **self.kwargs(),
        )
        project = FakeProjectManager.project
        library = project.find_elements_by_name(ARCADIA_OA_LIBRARY_PACKAGE)[0]
        instance = project.find_elements_by_name(
            level1_instance_package_name("Threat protection", digest)
        )[0]

        self.assertIs(library.owner, project.root)
        self.assertIs(instance.owner, project.root)
        self.assertIsNot(library, instance)
        entity_usage = project.find_elements_by_name("Control Center")[0]
        definition = entity_usage.part_definition[0]
        self.assertEqual(definition.name, "OperationalEntity")
        self.assertNotEqual(definition.owner, instance)


if __name__ == "__main__":
    unittest.main()
