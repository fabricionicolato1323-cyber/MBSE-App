from __future__ import annotations

import copy
import unittest

from sam_pysam_compat import (
    _install_reference_usage_subsetting_policy,
    install_relationship_reload_aliases,
    install_transactional_factory_fix,
)
from sam_reload_safe_factory import ReloadSafeFactory


class FakeElement:
    counter = 0

    def __init__(self, element_type: str, *, element_id: str | None = None, **kwargs):
        type(self).counter += 1
        self.id = element_id or f"fake-{type(self).counter}"
        self.element_type = element_type
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeProject:
    def __init__(self):
        self.elements: list[FakeElement] = []
        self._env: dict[str, FakeElement] = {}

    def add(self, *elements: FakeElement) -> None:
        for element in elements:
            self.elements.append(element)
            self._env[element.id] = element

    def find_element_by_id(self, element_id):
        return self._env.get(element_id)

    def find_elements_by_name(self, name):
        return [item for item in self.elements if getattr(item, "name", None) == name]

    def reload_objects(self):
        refreshed = [copy.copy(item) for item in self.elements]
        self.elements = refreshed
        self._env = {item.id: item for item in refreshed}


class StrictReferenceFactory:
    def __init__(self, project: FakeProject):
        self.project = project
        self.calls: list[tuple[str, dict]] = []

    def _create(self, kind: str, **kwargs):
        self.calls.append((kind, dict(kwargs)))
        element = FakeElement(kind, **kwargs)
        self.project.add(element)
        self.project.reload_objects()
        return element

    def create_reference_usage(self, **kwargs):
        if "referenced_feature" in kwargs:
            raise RuntimeError("referencedFeature is derived and cannot be submitted directly")
        return self._create("ReferenceUsage", **kwargs)

    def create_reference_subsetting(self, **kwargs):
        return self._create("ReferenceSubsetting", **kwargs)


class PySamTransactionalCompatibilityTests(unittest.TestCase):
    def test_transaction_factory_is_fixed_or_already_fixed_upstream(self) -> None:
        result = install_transactional_factory_fix()
        self.assertIn("required", result)
        self.assertIn("applied", result)
        self.assertIn("relationships", result)
        self.assertIn("reference_usage", result)

        from ansys.sam.sysml2.tools import Factory

        method = Factory._create_local_element_and_stack
        if result["required"]:
            self.assertTrue(result["applied"])
            self.assertTrue(getattr(method, "_mbse_level1_transaction_fix", False))
        else:
            # A future released PySAM may already contain the upstream correction.
            self.assertFalse(result["applied"])

    def test_located_in_reference_uses_reference_subsetting(self) -> None:
        _install_reference_usage_subsetting_policy()
        FakeElement.counter = 0
        project = FakeProject()
        owner = FakeElement("PartUsage", element_id="sam-actor", name="Actor")
        target = FakeElement("PartUsage", element_id="sam-place", name="Place")
        definition = FakeElement(
            "PartDefinition", element_id="sam-entity-def", name="OperationalEntity"
        )
        project.add(owner, target, definition)
        delegate = StrictReferenceFactory(project)
        factory = ReloadSafeFactory(project, delegate)

        result = factory.create_reference_usage(
            name="LOCATED_IN",
            owner=owner,
            reference_type=[definition],
            type_=[definition],
            referenced_feature=[target],
        )

        self.assertEqual(result.element_type, "ReferenceUsage")
        usage_calls = [payload for kind, payload in delegate.calls if kind == "ReferenceUsage"]
        subset_calls = [
            payload for kind, payload in delegate.calls if kind == "ReferenceSubsetting"
        ]
        self.assertEqual(len(usage_calls), 1)
        self.assertNotIn("referenced_feature", usage_calls[0])
        self.assertEqual(len(subset_calls), 1)
        self.assertEqual(subset_calls[0]["referenced_feature"].id, target.id)
        self.assertEqual(subset_calls[0]["owner"].id, result.id)
        self.assertEqual(subset_calls[0]["referencing_feature"].id, result.id)

    def test_located_in_adoption_falls_back_to_project_scope_and_subsetting(self) -> None:
        install_relationship_reload_aliases()
        import sam_level1_complete_incremental as complete

        project = FakeProject()
        actor = FakeElement("PartUsage", element_id="sam-actor", name="Actor")
        place = FakeElement("PartUsage", element_id="sam-place", name="Place")
        located = FakeElement(
            "ReferenceUsage",
            element_id="sam-located",
            name="LOCATED_IN",
            owner=actor,
        )
        subsetting = FakeElement(
            "ReferenceSubsetting",
            element_id="sam-located-subset",
            owner=located,
            referencing_feature=located,
            referenced_feature=[place],
        )
        project.add(actor, place, located, subsetting)

        context = complete._mbse_relationship_adoption_project_context
        token = context.set(project)
        try:
            matched = complete._match_existing(
                [],
                {
                    "type": "LOCATED_IN",
                    "source": "actor",
                    "target": "place",
                    "key": 0,
                },
                {"actor": actor.id, "place": place.id},
            )
        finally:
            context.reset(token)

        self.assertIsNotNone(matched)
        self.assertEqual(matched.id, located.id)


if __name__ == "__main__":
    unittest.main()
