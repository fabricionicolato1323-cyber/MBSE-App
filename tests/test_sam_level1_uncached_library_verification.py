from __future__ import annotations

import unittest

from sam_connection import SamSettings
from sam_level1_transactional import (
    ARCADIA_OA_LIBRARY_PACKAGE,
    ensure_arcadia_oa_library,
)


class Element:
    counter = 0

    def __init__(self, element_type: str, **kwargs):
        type(self).counter += 1
        self.id = f"fresh-{type(self).counter}"
        self.element_type = element_type
        for key, value in kwargs.items():
            setattr(self, key, value)


class ServerState:
    elements: list[Element] = []
    commits = 0


class CachedSnapshotProject:
    """A manager-local snapshot that does not mutate when a commit is published."""

    def __init__(self):
        self.root = Element("Package", name="Root")
        self.elements = list(ServerState.elements)
        self.pending: list[Element] = []
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
        ServerState.elements.extend(self.pending)
        ServerState.commits += 1
        # Deliberately keep ``self.elements`` unchanged. This reproduces the
        # stale manager/scripting-project view that motivated the regression.


class Connector:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class CachedProjectManager:
    instances = 0

    def __init__(self, connector):
        type(self).instances += 1
        self.connector = connector
        self.cached_project = CachedSnapshotProject()

    def get_scripting_project(self, project_id):
        return self.cached_project


class TransactionFactory:
    def __init__(self, project, connector):
        self.project = project
        self.connector = connector

    def __getattr__(self, name):
        if not name.startswith("create_"):
            raise AttributeError(name)
        element_type = "".join(part.capitalize() for part in name[len("create_"):].split("_"))

        def create(**kwargs):
            element = Element(element_type, **kwargs)
            self.project.pending.append(element)
            return element

        return create


class SamLevel1UncachedVerificationTests(unittest.TestCase):
    def setUp(self):
        Element.counter = 0
        ServerState.elements = []
        ServerState.commits = 0
        CachedProjectManager.instances = 0
        self.settings = SamSettings(
            server_url="https://sam.example.test",
            organization_id="org-1",
            project_id="project-1",
            access_token="secret",
            use_ssl=True,
        )

    def test_library_verification_uses_a_new_project_manager_after_commit(self):
        result = ensure_arcadia_oa_library(
            self.settings,
            connector_class=Connector,
            project_manager_class=CachedProjectManager,
            factory_class=TransactionFactory,
        )

        self.assertEqual(result["status"], "loaded")
        self.assertTrue(result["loaded"])
        self.assertEqual(ServerState.commits, 1)
        self.assertEqual(CachedProjectManager.instances, 2)
        self.assertEqual(
            len(
                [
                    element
                    for element in ServerState.elements
                    if getattr(element, "name", None) == ARCADIA_OA_LIBRARY_PACKAGE
                ]
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
