from __future__ import annotations

import unittest

from sam_reload_safe_factory import ReloadSafeFactory


class Element:
    def __init__(self, element_id: str):
        self.id = element_id


class Project:
    def __init__(self, elements):
        self.elements = {element.id: element for element in elements}

    def find_element_by_id(self, element_id):
        return self.elements.get(element_id)


class StrictFactory:
    def __init__(self, project):
        self.project = project
        self.calls = []

    def create_allocation_usage(self, **kwargs):
        raise AssertionError("AllocationUsage must not be used for capability support transport")

    def create_satisfy_requirement_usage(self, **kwargs):
        forbidden = {
            "source",
            "target",
            "source_feature",
            "target_feature",
            "related_feature",
            "is_directed",
        }
        self.assert_no_derived_connector_fields(kwargs, forbidden)
        self.calls.append(kwargs)
        created = Element("satisfy-1")
        self.project.elements[created.id] = created
        return created

    @staticmethod
    def assert_no_derived_connector_fields(kwargs, forbidden):
        unexpected = sorted(forbidden.intersection(kwargs))
        if unexpected:
            raise AssertionError(f"derived connector fields leaked into transport: {unexpected}")


class CapabilitySupportTransportTests(unittest.TestCase):
    def test_allocation_call_is_persisted_as_satisfy_requirement_usage(self):
        owner = Element("owner")
        capability = Element("capability")
        activity = Element("activity")
        project = Project([owner, capability, activity])
        delegate = StrictFactory(project)
        factory = ReloadSafeFactory(project, delegate)

        created = factory.create_allocation_usage(
            name="Supports capability",
            owner=owner,
            source=[capability],
            target=[activity],
            source_feature=capability,
            target_feature=[activity],
            related_feature=[capability, activity],
            is_directed=True,
        )

        self.assertEqual(created.id, "satisfy-1")
        self.assertEqual(len(delegate.calls), 1)
        payload = delegate.calls[0]
        self.assertIs(payload["owner"], owner)
        self.assertIs(payload["satisfied_requirement"], capability)
        self.assertIs(payload["satisfying_feature"], activity)
        self.assertEqual(payload["name"], "Supports capability")


if __name__ == "__main__":
    unittest.main()
