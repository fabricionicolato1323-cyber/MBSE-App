from __future__ import annotations

import unittest

from sam_level1_transactional import (
    ARCADIA_OA_LIBRARY_MARKER,
    ARCADIA_OA_LIBRARY_PACKAGE,
    ARCADIA_OA_NAMESPACE,
    _REQUIRED_DEFINITIONS,
    _children,
    _library_status_from_project,
)


class ReloadedElement:
    """Approximate the field shape produced by PySAM's scripting JSON mapper."""

    def __init__(self, element_id: str, name: str, *, owning_namespace=None):
        self._id = element_id
        self._name = name
        # Important regression condition: the derived collection exists but is empty.
        self._ownedElement = []
        if owning_namespace is not None:
            # ScriptingMapper maps JSON ``owningNamespace`` to ``_owningNamespace``.
            self._owningNamespace = owning_namespace


class ReloadedProject:
    def __init__(self, elements):
        self._env = {element._id: element for element in elements}

    def find_elements_by_name(self, name):
        return [element for element in self._env.values() if element._name == name]

    def find_element_by_id(self, element_id):
        return self._env.get(element_id)


class SamLevel1PostReloadOwnershipTests(unittest.TestCase):
    def _project(self):
        managed = ReloadedElement("managed-library", ARCADIA_OA_LIBRARY_PACKAGE)
        namespace = ReloadedElement(
            "managed-namespace",
            ARCADIA_OA_NAMESPACE,
            owning_namespace="managed-library",
        )
        marker = ReloadedElement(
            "managed-marker",
            ARCADIA_OA_LIBRARY_MARKER,
            owning_namespace="managed-library",
        )
        definitions = [
            ReloadedElement(
                f"managed-def-{index}",
                name,
                owning_namespace="managed-namespace",
            )
            for index, name in enumerate(_REQUIRED_DEFINITIONS, start=1)
        ]

        # Old Level 1 attempts can contain other ArcadiaOA namespaces and definition
        # names. The resolver must stay scoped to the managed library package.
        old_package = ReloadedElement("old-package", "MBSE_Level1_Old_12345678")
        old_namespace = ReloadedElement(
            "old-namespace",
            ARCADIA_OA_NAMESPACE,
            owning_namespace="old-package",
        )
        old_definition = ReloadedElement(
            "old-operational-entity",
            "OperationalEntity",
            owning_namespace="old-namespace",
        )
        return ReloadedProject(
            [
                managed,
                namespace,
                marker,
                *definitions,
                old_package,
                old_namespace,
                old_definition,
            ]
        )

    def test_empty_owned_element_does_not_hide_owning_namespace_children(self):
        project = self._project()
        managed = project.find_element_by_id("managed-library")
        names = {getattr(item, "_name", "") for item in _children(project, managed)}
        self.assertIn(ARCADIA_OA_NAMESPACE, names)
        self.assertIn(ARCADIA_OA_LIBRARY_MARKER, names)

    def test_fresh_reload_recognizes_complete_managed_library(self):
        project = self._project()
        status = _library_status_from_project(project)
        self.assertTrue(status["loaded"])
        self.assertEqual(status["package_id"], "managed-library")
        self.assertEqual(status["namespace_id"], "managed-namespace")
        self.assertTrue(status["completion_marker_scoped"])
        self.assertEqual(status["missing_definitions"], [])
        self.assertEqual(
            getattr(status["definitions"]["OperationalEntity"], "_id", None),
            "managed-def-1",
        )


if __name__ == "__main__":
    unittest.main()
