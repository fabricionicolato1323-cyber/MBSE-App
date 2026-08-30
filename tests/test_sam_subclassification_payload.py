from __future__ import annotations

import unittest

from sam_reload_safe_factory import ReloadSafeFactory


class FakeElement:
    def __init__(self, element_id: str):
        self.id = element_id


class FakeProject:
    def __init__(self):
        self.elements = {
            "actor": FakeElement("actor"),
            "entity": FakeElement("entity"),
        }

    def find_element_by_id(self, element_id):
        return self.elements.get(element_id)


class StrictSubclassificationFactory:
    def __init__(self):
        self.received = None

    def create_subclassification(self, **kwargs):
        if "source" in kwargs or "target" in kwargs:
            raise RuntimeError("Bad Request: derived relationship ends are not accepted")
        self.received = kwargs
        return kwargs["subclassifier"]


class SamSubclassificationPayloadTests(unittest.TestCase):
    def test_adapter_removes_derived_source_and_target(self):
        project = FakeProject()
        delegate = StrictSubclassificationFactory()
        factory = ReloadSafeFactory(project, delegate)

        actor = project.find_element_by_id("actor")
        entity = project.find_element_by_id("entity")
        result = factory.create_subclassification(
            owner=actor,
            subclassifier=actor,
            superclassifier=entity,
            source=[actor],
            target=[entity],
        )

        self.assertIs(result, actor)
        self.assertIsNotNone(delegate.received)
        self.assertNotIn("source", delegate.received)
        self.assertNotIn("target", delegate.received)
        self.assertIs(delegate.received["owner"], actor)
        self.assertIs(delegate.received["subclassifier"], actor)
        self.assertIs(delegate.received["superclassifier"], entity)


if __name__ == "__main__":
    unittest.main()
