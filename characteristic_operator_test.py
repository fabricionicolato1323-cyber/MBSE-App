from characteristic_operators import install_characteristic_operator_support
from graph_model import OAGraph


def main() -> None:
    install_characteristic_operator_support()
    model = OAGraph()

    ok, action, error = model.add_node("OperationalActivity", "Handle request")
    assert ok, error

    # 1. Single-value comparison operator is persisted and formatted.
    ok, error = model.add_characteristic(
        action,
        {
            "name": "Response time",
            "value_type": "number",
            "value": 5,
            "operator": "<=",
            "unit": "min",
        },
    )
    assert ok, error
    response_time = model.characteristics_for_node(action)[0]
    assert response_time["operator"] == "<="

    # 2. Range boundary operators are persisted independently.
    ok, goal, error = model.add_node("OperationalCapability", "Maintain service")
    assert ok, error
    ok, error = model.add_characteristic(
        goal,
        {
            "name": "Operating window",
            "value_type": "range",
            "lower_bound": 2,
            "lower_operator": ">",
            "upper_bound": 10,
            "upper_operator": "<=",
            "unit": "min",
        },
    )
    assert ok, error
    window = model.characteristics_for_node(goal)[0]
    assert window["lower_operator"] == ">"
    assert window["upper_operator"] == "<="

    # 3. Unsupported operators are rejected deterministically.
    ok, actor, error = model.add_node("OperationalActor", "Coordinator")
    assert ok, error
    ok, error = model.add_characteristic(
        actor,
        {
            "name": "Invalid comparison",
            "value_type": "number",
            "value": 3,
            "operator": "!=",
            "unit": "items",
        },
    )
    assert not ok and "operator" in error.casefold()

    # 4. Equal bounds cannot be combined with a strict boundary.
    ok, error = model.add_characteristic(
        actor,
        {
            "name": "Empty range",
            "value_type": "range",
            "lower_bound": 5,
            "lower_operator": ">",
            "upper_bound": 5,
            "upper_operator": "<=",
            "unit": "min",
        },
    )
    assert not ok and "inclusive" in error.casefold()

    # 5. Old saved semantics remain backward compatible.
    ok, entity, error = model.add_node("OperationalEntity", "Context")
    assert ok, error
    ok, error = model.add_characteristic(
        entity,
        {
            "name": "Legacy exact",
            "value_type": "number",
            "value": 7,
            "unit": "m",
        },
    )
    assert ok, error
    legacy_exact = model.characteristics_for_node(entity)[0]
    assert legacy_exact["operator"] == "="

    ok, error = model.add_characteristic(
        entity,
        {
            "name": "Legacy range",
            "value_type": "range",
            "lower_bound": 1,
            "upper_bound": 4,
            "unit": "m",
        },
    )
    assert ok, error
    legacy_range = model.characteristics_for_node(entity)[1]
    assert legacy_range["lower_operator"] == ">="
    assert legacy_range["upper_operator"] == "<="

    # 6. /show-compatible output carries the explicit comparison semantics.
    shown = model.friendly_show()
    assert "Response time: ≤ 5 min" in shown
    assert "Operating window: 2 < value ≤ 10 min" in shown
    assert "Legacy exact: = 7 m" in shown
    assert "Legacy range: 1 ≤ value ≤ 4 m" in shown

    print("Characteristic operator test passed (6 feature checks).")


if __name__ == "__main__":
    main()
