from graph_model import OAGraph


def main() -> None:
    model = OAGraph()

    ok, goal, error = model.add_node("OperationalCapability", "Maintain service")
    assert ok, error
    ok, actor, error = model.add_node("OperationalActor", "Coordinator")
    assert ok, error
    ok, action_a, error = model.add_node("OperationalActivity", "Coordinate requests")
    assert ok, error
    ok, action_b, error = model.add_node("OperationalActivity", "Report status")
    assert ok, error
    assert model.add_relation(actor, "PERFORMS", action_a)[0]
    assert model.add_relation(actor, "PERFORMS", action_b)[0]
    assert model.add_relation(action_a, "SUPPORTS_CAPABILITY", goal)[0]
    assert model.add_relation(action_b, "SUPPORTS_CAPABILITY", goal)[0]
    assert model.add_relation(action_a, "OPERATIONAL_EXCHANGE", action_b, name="Status information")[0]

    # 1. Single numeric value stays numeric and unit stays separate.
    ok, error = model.add_characteristic(
        action_a,
        {"name": "Duration", "value_type": "number", "value": "5", "unit": "minutes"},
    )
    assert ok, error
    duration = model.characteristics_for_node(action_a)[0]
    assert duration["value"] == 5 and isinstance(duration["value"], int)
    assert duration["unit"] == "minutes"

    # 2. Valid range persists explicit lower/upper bounds.
    ok, error = model.add_characteristic(
        goal,
        {"name": "Response window", "value_type": "range", "lower_bound": 5, "upper_bound": 10, "unit": "minutes"},
    )
    assert ok, error
    response = model.characteristics_for_node(goal)[0]
    assert response["lower_bound"] == 5
    assert response["upper_bound"] == 10

    # 3. Invalid range is blocked deterministically.
    ok, error = model.add_characteristic(
        actor,
        {"name": "Invalid", "value_type": "range", "lower_bound": 10, "upper_bound": 5, "unit": "minutes"},
    )
    assert not ok and "Lower bound" in error

    # 4. Duplicate names are blocked case-insensitively on the same owner.
    ok, error = model.add_characteristic(
        action_a,
        {"name": "duration", "value_type": "number", "value": 7, "unit": "minutes"},
    )
    assert not ok and "already exists" in error

    # 5. Text characteristics are supported without inventing values.
    ok, error = model.add_characteristic(
        actor,
        {"name": "Availability", "value_type": "text", "value": "On demand"},
    )
    assert ok, error
    assert model.characteristics_for_node(actor)[0]["value"] == "On demand"

    # 6. Interaction characteristics are stored on the exchange edge.
    source, target, key, _ = model.exchange_records()[0]
    ok, error = model.add_exchange_characteristic(
        source,
        target,
        key,
        {"name": "Frequency", "value_type": "range", "lower_bound": 1, "upper_bound": 3, "unit": "per hour"},
    )
    assert ok, error
    assert model.characteristics_for_exchange(source, target, key)[0]["upper_bound"] == 3

    # 7. /show-compatible output includes values and range bounds.
    shown = model.friendly_show()
    assert "Characteristics" in shown
    assert "Duration: 5 minutes" in shown
    assert "Response window: 5 .. 10 minutes" in shown
    assert "Frequency: 1 .. 3 per hour" in shown

    # 8. /check-compatible validation detects malformed persisted data.
    model.graph.nodes[actor]["characteristics"].append(
        {"name": "Broken range", "value_type": "range", "lower_bound": 9, "upper_bound": 2, "unit": "m"}
    )
    issues = model.completeness_messages()
    assert any("invalid characteristic" in item for item in issues)

    print("Characteristics test passed (8 feature checks).")


if __name__ == "__main__":
    main()
