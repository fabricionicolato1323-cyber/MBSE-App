from characteristic_operators import install_characteristic_operator_support
from graph_model import OAGraph


def main() -> None:
    install_characteristic_operator_support()
    model = OAGraph()

    ok, action, error = model.add_node("OperationalActivity", "Handle request")
    assert ok, error

    # 1. A percentage is a distinct structured value type.
    ok, error = model.add_characteristic(
        action,
        {
            "name": "Completion rate",
            "value_type": "percentage",
            "value": 95,
            "operator": ">=",
        },
    )
    assert ok, error
    percentage = model.characteristics_for_node(action)[0]
    assert percentage["value_type"] == "percentage"
    assert percentage["value"] == 95
    assert percentage["operator"] == ">="
    assert percentage["unit"] == "%"

    # 2. Percentage ranges keep independent boundary operators.
    ok, goal, error = model.add_node("OperationalCapability", "Maintain service")
    assert ok, error
    ok, error = model.add_characteristic(
        goal,
        {
            "name": "Utilization band",
            "value_type": "percentage_range",
            "lower_bound": 20,
            "lower_operator": ">=",
            "upper_bound": 40,
            "upper_operator": "<",
        },
    )
    assert ok, error
    band = model.characteristics_for_node(goal)[0]
    assert band["value_type"] == "percentage_range"
    assert band["lower_operator"] == ">="
    assert band["upper_operator"] == "<"
    assert band["unit"] == "%"

    # 3. Percentage values are not artificially limited to 0..100.
    ok, entity, error = model.add_node("OperationalEntity", "Context")
    assert ok, error
    ok, error = model.add_characteristic(
        entity,
        {
            "name": "Peak relative load",
            "value_type": "percentage",
            "value": 125,
            "operator": "<=",
        },
    )
    assert ok, error

    # 4. /show-compatible output uses percentage notation without a space.
    shown = model.friendly_show()
    assert "Completion rate: ≥ 95%" in shown
    assert "Utilization band: 20% ≤ value < 40%" in shown
    assert "Peak relative load: ≤ 125%" in shown

    print("Percentage characteristic test passed (4 feature checks).")


if __name__ == "__main__":
    main()
