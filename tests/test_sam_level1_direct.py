from __future__ import annotations

import copy
import unittest

from sam_connection import SamSettings
from sam_level1_direct import (
    level1_completion_marker_name,
    level1_staging_package_name,
    sync_level1_to_sam_direct,
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
        self.root = FakeElement("Package", name="API Test")
        self.elements = [self.root]
        self.transaction_started = 0
        self.transaction_stopped = 0

    def get_root_package(self):
        return self.root

    def find_element_by_id(self, element_id):
        return next(
            (element for element in self.elements if element.id == element_id),
            None,
        )

    def find_elements_by_name(self, name):
        return [element for element in self.elements if getattr(element, "name", None) == name]

    def start_transactional_mode(self):
        self.transaction_started += 1

    def stop_transactional_mode(self):
        self.transaction_stopped += 1

    def replace_all_instances(self):
        """Mimic PySAM project.reload() replacing every scripting object."""
        root_id = self.root.id
        self.elements = [copy.copy(element) for element in self.elements]
        self.root = self.find_element_by_id(root_id)


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
        element_type = "".join(
            part.capitalize() for part in name[len("create_"):].split("_")
        )

        def create(**kwargs):
            element = FakeElement(element_type, **kwargs)
            self.project.elements.append(element)
            return element

        return create


class ReloadingFakeFactory(FakeFactory):
    """Reject stale element references and reload after every direct create."""

    def _assert_current(self, value):
        if isinstance(value, (list, tuple, set)):
            for item in value:
                self._assert_current(item)
            return
        if isinstance(value, dict):
            for item in value.values():
                self._assert_current(item)
            return
        if not isinstance(value, FakeElement):
            return
        current = self.project.find_element_by_id(value.id)
        if current is not value:
            raise RuntimeError(f"stale element reference: {value.id}")

    def __getattr__(self, name):
        create = super().__getattr__(name)

        def create_and_reload(**kwargs):
            for value in kwargs.values():
                self._assert_current(value)
            created = create(**kwargs)
            self.project.replace_all_instances()
            return created

        return create_and_reload


class DocumentationRejectingFactory(FakeFactory):
    """Mimic the live SAM behavior observed during Gate 1B."""

    def create_documentation(self, **kwargs):
        raise RuntimeError("Bad Request")


class AllAnnotationRejectingFactory(DocumentationRejectingFactory):
    def create_comment(self, **kwargs):
        raise RuntimeError("Bad Request")


class SamLevel1DirectTests(unittest.TestCase):
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
            "graph": {"model_name": "Direct test"},
            "nodes": [
                {"id": "entity", "type": "OperationalEntity", "name": "Control Center"},
                {"id": "activity", "type": "OperationalActivity", "name": "Detect threat"},
            ],
            "edges": [
                {"source": "entity", "target": "activity", "type": "PERFORMS"},
            ],
        }

    def _sync(self, factory_class=FakeFactory):
        digest = level1_snapshot_digest(self.model, [])
        return sync_level1_to_sam_direct(
            self.model,
            scenarios=[],
            settings=self.settings,
            expected_digest=digest,
            connector_class=FakeConnector,
            project_manager_class=FakeProjectManager,
            factory_class=factory_class,
        )

    def test_direct_writer_never_enters_transactional_mode(self):
        digest = level1_snapshot_digest(self.model, [])
        result = self._sync()

        project = FakeProjectManager.project
        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["mode"], "verified_direct_create_snapshot")
        self.assertEqual(result["retry_policy"], "unique_staging_no_delete")
        self.assertEqual(project.transaction_started, 0)
        self.assertEqual(project.transaction_stopped, 0)
        self.assertTrue(project.find_elements_by_name(result["package_name"]))
        self.assertTrue(
            project.find_elements_by_name(level1_completion_marker_name(digest))
        )
        self.assertEqual(result["cleanup"]["removed_incomplete_staging_packages"], 0)

    def test_writer_rebinds_every_reference_after_direct_create_reload(self):
        result = self._sync(ReloadingFakeFactory)
        self.assertEqual(result["status"], "synced")
        self.assertTrue(
            FakeProjectManager.project.find_elements_by_name(result["package_name"])
        )

    def test_completed_snapshot_is_idempotent(self):
        first = self._sync()
        second = self._sync()
        self.assertEqual(first["status"], "synced")
        self.assertEqual(second["status"], "already_synced")
        self.assertFalse(second["sam_write_performed"])

    def test_incomplete_staging_does_not_block_retry_or_require_delete(self):
        digest = level1_snapshot_digest(self.model, [])
        from sam_level1_sync import build_level1_sync_plan

        plan = build_level1_sync_plan(
            self.model,
            scenarios=[],
            project_id=self.settings.project_id,
        )
        stale_name = level1_staging_package_name(plan["package_name"], "oldretry")

        class DeleteRejectingElement(FakeElement):
            def delete(self):
                raise RuntimeError("Bad Request")

        stale = DeleteRejectingElement("Package", name=stale_name)
        FakeProjectManager.project.elements.append(stale)

        result = self._sync()
        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["retry_policy"], "unique_staging_no_delete")
        self.assertEqual(result["cleanup"]["removed_incomplete_staging_packages"], 0)
        self.assertIn(stale, FakeProjectManager.project.elements)
        self.assertNotEqual(result["staging_package_name"], stale_name)
        self.assertTrue(
            result["staging_package_name"].startswith(
                level1_staging_package_name(plan["package_name"]) + "_"
            )
        )
        self.assertTrue(
            FakeProjectManager.project.find_elements_by_name(
                level1_completion_marker_name(digest)
            )
        )

    def test_documentation_rejection_falls_back_to_comment(self):
        result = self._sync(DocumentationRejectingFactory)
        self.assertEqual(result["status"], "synced")
        self.assertTrue(result["metadata_warnings"])
        self.assertIn("used Comment annotations", result["metadata_warnings"][0])
        created_types = {
            element.element_type for element in FakeProjectManager.project.elements
        }
        self.assertIn("Comment", created_types)

    def test_all_annotation_rejection_does_not_block_semantic_sync(self):
        result = self._sync(AllAnnotationRejectingFactory)
        self.assertEqual(result["status"], "synced")
        self.assertTrue(result["metadata_warnings"])
        self.assertIn("annotations were skipped", result["metadata_warnings"][0])
        self.assertTrue(
            FakeProjectManager.project.find_elements_by_name(result["package_name"])
        )


if __name__ == "__main__":
    unittest.main()
