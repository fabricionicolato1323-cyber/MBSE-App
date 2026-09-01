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


def _fixture():
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
    return factory, packages, definitions, analysis


def test_nested_usage_is_owned_by_membership_not_parallel_to_it():
    factory, packages, definitions, analysis = _fixture()

    elements, _ = create_projection_nodes(
        factory,
        analysis=analysis,
        definitions=definitions,
        packages=packages,
    )

    memberships = [e for e in factory.elements if e.element_type == "FeatureMembership"]
    assert len(memberships) == 4

    activity = elements["a1"]
    membership = activity.owner

    assert membership.element_type == "FeatureMembership"
    assert membership.owner is elements["actor"]
    assert membership.membership_owning_namespace is elements["actor"]
    assert membership.owning_type is elements["actor"]
    assert membership.member_element is activity
    assert membership.owned_member_element is activity
    assert membership.owned_member_feature is activity

    assert activity.owning_feature_membership is membership
    assert activity.owning_namespace is elements["actor"]
    assert activity.featuring_type == [elements["actor"]]
    assert activity.is_composite is True
    assert activity.owner is not elements["actor"]


def test_nested_part_and_decomposed_activity_follow_same_ownership_pattern():
    factory, packages, definitions, analysis = _fixture()

    elements, _ = create_projection_nodes(
        factory,
        analysis=analysis,
        definitions=definitions,
        packages=packages,
    )

    actor = elements["actor"]
    assert actor.owner.element_type == "FeatureMembership"
    assert actor.owner.owner is elements["entity"]
    assert actor.owning_feature_membership is actor.owner
    assert actor.is_composite is True

    child_activity = elements["a2"]
    assert child_activity.owner.element_type == "FeatureMembership"
    assert child_activity.owner.owner is elements["a1"]
    assert child_activity.owning_namespace is elements["a1"]
    assert child_activity.is_composite is True


def test_perform_actions_are_owned_by_feature_memberships():
    factory, packages, definitions, analysis = _fixture()

    elements, _ = create_projection_nodes(
        factory,
        analysis=analysis,
        definitions=definitions,
        packages=packages,
    )
    create_projection_scenarios(
        factory,
        analysis=analysis,
        elements=elements,
        definitions=definitions,
        packages=packages,
    )

    scenario = next(
        e
        for e in factory.elements
        if e.element_type == "ActionUsage" and getattr(e, "name", None) == "Nominal"
    )
    perform_steps = [e for e in factory.elements if e.element_type == "PerformActionUsage"]
    assert len(perform_steps) == 2

    for step in perform_steps:
        membership = step.owner
        assert membership.element_type == "FeatureMembership"
        assert membership.owner is scenario
        assert membership.owned_member_feature is step
        assert step.owning_feature_membership is membership
        assert step.owning_namespace is scenario
        assert step.is_composite is True
