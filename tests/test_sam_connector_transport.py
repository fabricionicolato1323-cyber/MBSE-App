from __future__ import annotations

import copy
import unittest

from sam_reload_safe_factory import ReloadSafeFactory


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
        self.elements: list[FakeElement] = []

    def find_element_by_id(self, element_id):
        return next((item for item in self.elements if item.id == element_id), None)

    def reload_objects(self):
        self.elements = [copy.copy(item) for item in self.elements]


class StrictConnectorFactory:
    forbidden = {
        "source",
        "target",
        "source_feature",
        "target_feature",
        "related_feature",
        "connector_end",
    }

    def __init__(self, project: FakeProject):
        self.project = project
        self.calls: list[tuple[str, dict]] = []

    def _create(self, kind: str, **kwargs):
        self.calls.append((kind, dict(kwargs)))
        element = FakeElement(kind, **kwargs)
        self.project.elements.append(element)
        self.project.reload_objects()
        return element

    def create_connection_usage(self, **kwargs):
        overlap = self.forbidden.intersection(kwargs)
        if overlap:
            raise RuntimeError(f"derived connector fields supplied: {sorted(overlap)}")
        return self._create("ConnectionUsage", **kwargs)

    def create_flow_connection_usage(self, **kwargs):
        overlap = self.forbidden.intersection(kwargs)
        if overlap:
            raise RuntimeError(f"derived connector fields supplied: {sorted(overlap)}")
        return self._create("FlowConnectionUsage", **kwargs)

    def create_reference_usage(self, **kwargs):
        return self._create("ReferenceUsage", **kwargs)

    def create_reference_subsetting(self, **kwargs):
        return self._create("ReferenceSubsetting", **kwargs)


class SamConnectorTransportTests(unittest.TestCase):
    def setUp(self):
        FakeElement.counter = 0
        self.project = FakeProject()
        self.owner = FakeElement("PartUsage", name="context")
        self.source = FakeElement("PartUsage", name="source")
        self.target = FakeElement("PartUsage", name="target")
        self.definition = FakeElement("ConnectionDefinition", name="CommunicationMean")
        self.flow_definition = FakeElement("FlowDefinition", name="OperationalExchange")
        self.project.elements.extend(
            [self.owner, self.source, self.target, self.definition, self.flow_definition]
        )
        self.delegate = StrictConnectorFactory(self.project)
        self.factory = ReloadSafeFactory(self.project, self.delegate)

    def _assert_binary_ends(self, connector_kind: str):
        calls = self.delegate.calls
        connector_calls = [payload for kind, payload in calls if kind == connector_kind]
        self.assertEqual(len(connector_calls), 1)
        self.assertFalse(StrictConnectorFactory.forbidden.intersection(connector_calls[0]))

        end_calls = [payload for kind, payload in calls if kind == "ReferenceUsage"]
        subset_calls = [payload for kind, payload in calls if kind == "ReferenceSubsetting"]
        self.assertEqual(len(end_calls), 2)
        self.assertEqual(len(subset_calls), 2)
        self.assertTrue(all(payload.get("is_end") is True for payload in end_calls))
        referenced_ids = {
            payload["referenced_feature"].id for payload in subset_calls
        }
        self.assertEqual(referenced_ids, {self.source.id, self.target.id})
        for payload in subset_calls:
            self.assertEqual(
                payload["referencing_feature"].id,
                payload["owner"].id,
            )

    def test_connection_usage_builds_reference_ends(self):
        result = self.factory.create_connection_usage(
            name="Radio",
            owner=self.owner,
            connection_definition=[self.definition],
            source=[self.source],
            target=[self.target],
            source_feature=self.source,
            target_feature=[self.target],
            related_feature=[self.source, self.target],
            is_directed=False,
        )
        self.assertEqual(result.element_type, "ConnectionUsage")
        self._assert_binary_ends("ConnectionUsage")

    def test_flow_connection_usage_builds_reference_ends(self):
        result = self.factory.create_flow_connection_usage(
            name="Threat information",
            owner=self.owner,
            flow_connection_definition=[self.flow_definition],
            source=[self.source],
            target=[self.target],
            source_feature=self.source,
            target_feature=[self.target],
            related_feature=[self.source, self.target],
            is_directed=True,
        )
        self.assertEqual(result.element_type, "FlowConnectionUsage")
        self._assert_binary_ends("FlowConnectionUsage")


if __name__ == "__main__":
    unittest.main()
