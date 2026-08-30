from characteristic_edit import install_characteristic_edit_support
from characteristic_operators import install_characteristic_operator_support
from graph_model import OAGraph


install_characteristic_operator_support()
install_characteristic_edit_support()


def test_node_characteristic_can_be_replaced_with_existing_validation():
    model = OAGraph()
    ok, node_id, error = model.add_node("OperationalActivity", "Observe area")
    assert ok, error
    assert model.add_characteristic(
        node_id,
        {"name": "Response time", "value_type": "number", "value": 5, "unit": "s", "operator": "<="},
    ) == (True, "")

    assert model.replace_characteristic(
        node_id,
        0,
        {"name": "Response time", "value_type": "number", "value": 3, "unit": "s", "operator": "<="},
    ) == (True, "")

    value = model.characteristics_for_node(node_id)[0]
    assert value["name"] == "Response time"
    assert value["value"] == 3
    assert value["operator"] == "<="


def test_node_characteristic_replacement_rejects_duplicate_name():
    model = OAGraph()
    ok, node_id, error = model.add_node("OperationalActivity", "Observe area")
    assert ok, error
    assert model.add_characteristic(
        node_id,
        {"name": "Response time", "value_type": "number", "value": 5, "unit": "s"},
    ) == (True, "")
    assert model.add_characteristic(
        node_id,
        {"name": "Confidence", "value_type": "percentage", "value": 90},
    ) == (True, "")

    ok, error = model.replace_characteristic(
        node_id,
        0,
        {"name": "Confidence", "value_type": "percentage", "value": 95},
    )
    assert ok is False
    assert "already exists" in error
    assert [item["name"] for item in model.characteristics_for_node(node_id)] == [
        "Response time",
        "Confidence",
    ]


def test_exchange_characteristic_can_be_replaced_and_undone():
    model = OAGraph()
    ok, source_id, error = model.add_node("OperationalActivity", "Send status")
    assert ok, error
    ok, target_id, error = model.add_node("OperationalActivity", "Receive status")
    assert ok, error
    assert model.add_relation(
        source_id,
        "OPERATIONAL_EXCHANGE",
        target_id,
        name="Status",
    ) == (True, "")
    source, target, key, _name = model.exchange_records()[0]
    assert model.add_exchange_characteristic(
        source,
        target,
        key,
        {"name": "Latency", "value_type": "range", "lower_bound": 1, "upper_bound": 4, "unit": "s"},
    ) == (True, "")

    assert model.replace_exchange_characteristic(
        source,
        target,
        key,
        0,
        {"name": "Latency", "value_type": "range", "lower_bound": 1, "upper_bound": 2, "unit": "s"},
    ) == (True, "")
    assert model.characteristics_for_exchange(source, target, key)[0]["upper_bound"] == 2

    assert model.undo() is True
    assert model.characteristics_for_exchange(source, target, key)[0]["upper_bound"] == 4
