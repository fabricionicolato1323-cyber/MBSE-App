from __future__ import annotations

from types import SimpleNamespace

from sam_full_projection_writer import create_projection_nodes, create_projection_scenarios


class Element:
    counter = 0

    def __init__(self, element_type: str, **kwargs):
        type(self).counter += 1
        self.id = f"element-{type(self).counter}"
        self.element_type = element_type
        for key, value in kwargs.items():
            setattr(self, key, value)


class Factory:
    def __init__(self):
        self.elements = []

    def __getattr__(self, name):
        if not name.startswith("create_"):
            raise AttributeError(name)
        element_type = "".join(part.capitalize() for part in name[7:].split("_"))

        def create(**kwargs):
            element = Element(element_type, **kwargs)
            self.elements.append(element)
            return element

        return create


def _definition(name: str) -> Element:
    return Element("Definition", name=name)


def test_nested_usages_receive_owning_feature_memberships():
    factory = Factory()
    packages = {
        "structure": Element("Package", name="Structure"),
        "requirements": Element("Package", name="Requirements"),
        "scenarios": Element("Package", name="Scenarios"),
    }
    definitions = {
        "OperationalEntity": _definition("Operational Entity"),
        "OperationalActor": _definition("Operational Actor"),
        "OperationalActivity": _definition("Operational Activity"),
        "OperationalCapability": _definition("Operational Capability"),
        "OperationalScenario": _definition("Operational Scenario"),
    }
    analysis = SimpleNamespace(
        node_by_id={
            "entity": {"id": "entity", "type": "OperationalEntity", "name": "Vehicle"},
            "actor": {"id": "actor", "type": "OperationalActor", "name": "Driver"},
            "a1": {"id": "a1", "type": "OperationalActivity", "name": "Observe"},
            "a2": {"id": "a2", "type": "OperationalActivity", "name": "Decide"},
            "cap1": {"id": "cap1", "type": "OperationalCapability", "name": "Operate"},
            "cap2": {
                "id": "cap2",
                "type": "OperationalCapability",
                "name": "Operate safely",
            },
        },
        participant_parent={"actor": "entity"},
        activity_parent={"a2": "a1"},
        capability_parent={"cap2": "cap1"},
        effective_performer={"a1": "actor", "a2": "actor"},
        scenarios=[
            {
                "id": "s1",
                "name": "Nominal",
                "valid": True,
                "steps": [
                    {"kind": "activity", "activity_id": "a1"},
                    {"kind": "activity", "activity_id": "a2"},
                ],
            }
        ],
    )

    elements, _ = create_projection_nodes(
        factory,
        analysis=analysis,
        definitions=definitions,
        packages=packages,
    )

    memberships = [e for e in factory.elements if e.element_type == "FeatureMembership"]
    assert len(memberships) == 4  # nested actor, two activities, decomposed capability

    a1_membership = next(
        m for m in memberships if m.owned_member_feature is elements["a1"]
    )
    assert a1_membership.owner is elements["actor"]
    assert a1_membership.owning_type is elements["actor"]
    assert a1_membership.membership_owning_namespace is elements["actor"]
    assert a1_membership.member_element is elements["a1"]
    assert a1_membership.owned_member_element is elements["a1"]

    a2_membership = next(
        m for m in memberships if m.owned_member_feature is elements["a2"]
    )
    assert a2_membership.owner is elements["a1"]
    assert a2_membership.owning_type is elements["a1"]

    create_projection_scenarios(
        factory,
        analysis=analysis,
        elements=elements,
        definitions=definitions,
        packages=packages,
    )

    memberships = [e for e in factory.elements if e.element_type == "FeatureMembership"]
    perform_steps = [e for e in factory.elements if e.element_type == "PerformActionUsage"]
    assert len(perform_steps) == 2
    for step in perform_steps:
        membership = next(m for m in memberships if m.owned_member_feature is step)
        assert membership.owner is step.owner
        assert membership.owning_type is step.owner
