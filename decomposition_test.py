from graph_model import OAGraph


def main() -> None:
    model = OAGraph()

    ok, goal, error = model.add_node("OperationalCapability", "Maintain safe operations")
    assert ok, error
    ok, sub_goal, error = model.add_node("OperationalCapability", "Maintain operational awareness")
    assert ok, error
    ok, other_goal, error = model.add_node("OperationalCapability", "Maintain service continuity")
    assert ok, error

    ok, actor, error = model.add_node("OperationalActor", "Coordinator")
    assert ok, error
    ok, child_actor, error = model.add_node("OperationalActor", "Dispatcher")
    assert ok, error
    ok, entity, error = model.add_node(
        "OperationalEntity",
        "Operations Team",
        expects_activity=True,
        nature="team_or_collective",
    )
    assert ok, error
    ok, sub_entity, error = model.add_node(
        "OperationalEntity",
        "Regional Unit",
        expects_activity=True,
        nature="organizational_unit",
    )
    assert ok, error
    ok, other_entity, error = model.add_node(
        "OperationalEntity",
        "Other Team",
        expects_activity=True,
        nature="team_or_collective",
    )
    assert ok, error

    ok, parent_action, error = model.add_node("OperationalActivity", "Coordinate response")
    assert ok, error
    ok, child_action, error = model.add_node("OperationalActivity", "Assess situation")
    assert ok, error
    ok, second_parent_action, error = model.add_node("OperationalActivity", "Manage operations")
    assert ok, error

    assert model.add_relation(actor, "PERFORMS", parent_action)[0]
    assert model.add_relation(parent_action, "SUPPORTS_CAPABILITY", goal)[0]
    assert model.add_characteristic(
        parent_action,
        {"name": "Duration", "value_type": "range", "lower_bound": 1, "upper_bound": 5, "unit": "minutes"},
    )[0]

    # 1. Goal decomposition is supported.
    ok, error = model.add_relation(goal, "DECOMPOSES", sub_goal)
    assert ok, error
    assert model.decomposition_parent(sub_goal) == goal

    # 2. Action decomposition is supported.
    ok, error = model.add_relation(parent_action, "DECOMPOSES", child_action)
    assert ok, error
    assert child_action in model.decomposition_children(parent_action)

    # 3. Parent performer is not inherited automatically.
    assert model.participants_for_activity(child_action) == []

    # 4. Parent goal connection is not inherited automatically.
    assert not model.has_relation(child_action, "SUPPORTS_CAPABILITY", goal)

    # 5. Parent characteristics are not inherited automatically.
    assert model.characteristics_for_node(child_action) == []

    # 6. Self-decomposition is blocked.
    ok, error = model.add_relation(other_goal, "DECOMPOSES", other_goal)
    assert not ok and "itself" in error

    # 7. Cross-type decomposition is blocked.
    ok, error = model.add_relation(goal, "DECOMPOSES", child_action)
    assert not ok and "goals" in error and "actions" in error

    # 8. A child cannot have two decomposition parents.
    ok, error = model.add_relation(second_parent_action, "DECOMPOSES", child_action)
    assert not ok and "another decomposition parent" in error

    # 9. Goal/action cycles are blocked.
    ok, error = model.add_relation(sub_goal, "DECOMPOSES", goal)
    assert not ok and "cycle" in error

    # 10. Participant/context composition supports entity -> entity.
    ok, error = model.add_relation(entity, "CONTAINS", sub_entity)
    assert ok, error
    assert model.decomposition_parent(sub_entity) == entity
    assert sub_entity in model.decomposition_children(entity)

    # 11. Participant/context composition supports entity -> actor.
    ok, error = model.add_relation(entity, "CONTAINS", actor)
    assert ok, error
    ok, error = model.add_relation(sub_entity, "CONTAINS", child_actor)
    assert ok, error
    assert model.decomposition_parent(actor) == entity
    assert model.decomposition_parent(child_actor) == sub_entity

    # 12. Actors remain structural leaves.
    ok, error = model.add_relation(actor, "CONTAINS", other_entity)
    assert not ok

    # 13. A participant/context child cannot have two structural parents.
    ok, error = model.add_relation(other_entity, "CONTAINS", child_actor)
    assert not ok and "already part" in error

    # 14. Participant/context composition cycles are blocked.
    ok, error = model.add_relation(sub_entity, "CONTAINS", entity)
    assert not ok and "cycle" in error

    # Explicitly assign the smaller action only after the decomposition exists.
    assert model.add_relation(actor, "PERFORMS", child_action)[0]
    assert model.add_relation(child_action, "SUPPORTS_CAPABILITY", sub_goal)[0]

    # 15. /show-compatible output presents all three hierarchy types and characteristics.
    shown = model.friendly_show()
    assert "Composition / decomposition" in shown
    assert "Maintain safe operations" in shown
    assert "Maintain operational awareness" in shown
    assert "Coordinate response" in shown
    assert "Assess situation" in shown
    assert "Operations Team" in shown
    assert "Regional Unit" in shown
    assert "Coordinator" in shown
    assert "Dispatcher" in shown
    assert "Characteristics" in shown
    assert "Duration: 1 .. 5 minutes" in shown

    # 16. /check-compatible validation detects malformed persisted cycles.
    model.graph.add_edge(sub_goal, goal, type="DECOMPOSES")
    issues = model.completeness_messages()
    assert any("decomposition contains a cycle" in item for item in issues)

    print("Decomposition test passed (16 feature checks).")


if __name__ == "__main__":
    main()
