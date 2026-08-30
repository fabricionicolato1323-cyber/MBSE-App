from __future__ import annotations

import unittest

from sam_connection import SamSettings
from sam_level1_managed_direct import (
    ensure_arcadia_oa_library_direct,
    sync_level1_to_sam_managed_direct,
)
from sam_level1_sync import level1_snapshot_digest
from sam_level1_transactional import ARCADIA_OA_LIBRARY_PACKAGE


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

    def get_root_package(self):
        return self.root

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


class ManagedDirectTests(unittest.TestCase):
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
            "graph": {"model_name": "Threat Protection"},
            "nodes": [
                {"id": "entity", "type": "OperationalEntity", "name": "Control Center"},
                {"id": "activity", "type": "OperationalActivity", "name": "Detect Threat"},
            ],
            "edges": [
                {"source": "entity", "target": "activity", "type": "PERFORMS"},
            ],
        }

    def kwargs(self):
        return {
            "connector_class": Connector,
            "project_manager_class": Manager,
            "factory_class": Factory,
        }

    def test_library_is_created_once_and_reused(self):
        first = ensure_arcadia_oa_library_direct(self.settings, **self.kwargs())
        second = ensure_arcadia_oa_library_direct(self.settings, **self.kwargs())

        self.assertEqual(first["status"], "loaded")
        self.assertEqual(second["status"], "already_loaded")
        libraries = Manager.project.find_elements_by_name(ARCADIA_OA_LIBRARY_PACKAGE)
        self.assertEqual(len(libraries), 1)
        self.assertFalse(
            any(
                getattr(item, "name", "").startswith(ARCADIA_OA_LIBRARY_PACKAGE + "__INCOMPLETE")
                and getattr(item, "name", "") == ARCADIA_OA_LIBRARY_PACKAGE
                for item in Manager.project.elements
            )
        )

    def test_same_snapshot_is_idempotent_and_does_not_duplicate_library(self):
        digest = level1_snapshot_digest(self.model, [])
        first = sync_level1_to_sam_managed_direct(
            self.model,
            scenarios=[],
            settings=self.settings,
            expected_digest=digest,
            **self.kwargs(),
        )
        count_after_first = len(Manager.project.elements)
        second = sync_level1_to_sam_managed_direct(
            self.model,
            scenarios=[],
            settings=self.settings,
            expected_digest=digest,
            **self.kwargs(),
        )

        self.assertEqual(first["status"], "synced")
        self.assertEqual(second["status"], "already_synced")
        self.assertEqual(len(Manager.project.elements), count_after_first)
        self.assertEqual(
            len(Manager.project.find_elements_by_name(ARCADIA_OA_LIBRARY_PACKAGE)),
            1,
        )
        self.assertTrue(first["package_name"].startswith("MBSE_Instance_Threat_Protection_"))
        self.assertFalse(first["completion_marker_required"])

    def test_second_model_reuses_library_but_creates_second_instance(self):
        first_digest = level1_snapshot_digest(self.model, [])
        first = sync_level1_to_sam_managed_direct(
            self.model,
            scenarios=[],
            settings=self.settings,
            expected_digest=first_digest,
            **self.kwargs(),
        )
        second_model = {
            **self.model,
            "graph": {"model_name": "Threat Protection Variant"},
        }
        second_digest = level1_snapshot_digest(second_model, [])
        second = sync_level1_to_sam_managed_direct(
            second_model,
            scenarios=[],
            settings=self.settings,
            expected_digest=second_digest,
            **self.kwargs(),
        )

        self.assertEqual(first["status"], "synced")
        self.assertEqual(second["status"], "synced")
        self.assertEqual(
            len(Manager.project.find_elements_by_name(ARCADIA_OA_LIBRARY_PACKAGE)),
            1,
        )
        self.assertNotEqual(first["package_name"], second["package_name"])


if __name__ == "__main__":
    unittest.main()
