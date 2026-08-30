from __future__ import annotations

from graph_model import OAGraph
from loaded_model_deletion import (
    LoadedModelDeletionMixin,
    build_characteristic_deletion_preview,
    build_edge_deletion_preview,
    build_node_deletion_preview,
    delete_characteristic,
    delete_edge,
    delete_node,
)


def sample_model() -> tuple[OAGraph, dict[str, str], tuple[str, str, object]]:
    model = OAGraph()
    ok, capability, _ = model.add_node("OperationalCapability", "Respond to threat")
    assert ok
    ok, operator, _ = model.add_node("OperationalActor", "Operator")
    assert ok
    ok, center, _ = model.add_node("OperationalEntity", "Control Center")
    assert ok
    ok, detect, _ = model.add_node("OperationalActivity", "Detect Threat")
    assert ok
    ok, assess, _ = model.add_node("OperationalActivity", "Assess Threat")
    assert ok

    assert model.add_relation(operator, "PERFORMS", detect)[0]
    assert model.add_relation(center, "PERFORMS", assess)[0]
    assert model.add_relation(detect, "SUPPORTS_CAPABILITY", capability)[0]
    assert model.add_relation(
        detect,
        "OPERATIONAL_EXCHANGE",
        assess,
        name="Threat Information",
    )[0]

    exchange = next(
        (source, target, key)
        for source, target, key, data in model.graph.edges(keys=True, data=True)
        if data.get("type") == "OPERATIONAL_EXCHANGE"
    )
    source, target, exchange_key = exchange
    assert model.add_relation(
        operator,
        "COMMUNICATION_MEAN",
        center,
        name="Radio",
        exchange_refs=[
            {
                "source_activity_id": source,
                "target_activity_id": target,
                "edge_key": exchange_key,
                "exchange_name": "Threat Information",
            }
        ],
    )[0]

    return (
        model,
        {
            "capability": capability,
            "operator": operator,
            "center": center,
            "detect": detect,
            "assess": assess,
        },
        exchange,
    )


def test_delete_is_a_loaded_model_intent() -> None:
    assert "delete" in LoadedModelDeletionMixin._LOADED_INTENTS


def test_activity_preview_marks_target_and_side_effects_without_mutating() -> None:
    model, ids, exchange = sample_model()
    before_nodes = set(model.graph.nodes)
    before_edges = list(model.graph.edges(keys=True))

    preview = build_node_deletion_preview(model, ids["detect"])

    assert preview["active"] is True
    assert preview["target"]["kind"] == "node"
    assert preview["target_node_ids"] == [ids["detect"]]
    assert ids["operator"] in preview["impact_node_ids"]
    assert ids["assess"] in preview["impact_node_ids"]
    assert any(edge["type"] == "OPERATIONAL_EXCHANGE" for edge in preview["impact_edges"])
    assert any(edge["type"] == "COMMUNICATION_MEAN" for edge in preview["impact_edges"])
    assert any("no remaining assigned activity" in effect for effect in preview["effects"])

    assert set(model.graph.nodes) == before_nodes
    assert list(model.graph.edges(keys=True)) == before_edges
    assert model.graph.has_edge(*exchange)


def test_confirmed_activity_delete_removes_incident_edges_and_scrubs_exchange_refs() -> None:
    model, ids, _exchange = sample_model()

    delete_node(model, ids["detect"])

    assert ids["detect"] not in model.graph
    communication = next(
        data
        for _source, _target, _key, data in model.graph.edges(keys=True, data=True)
        if data.get("type") == "COMMUNICATION_MEAN"
    )
    assert communication.get("exchange_refs") == []
    assert ids["operator"] in model.graph
    assert ids["assess"] in model.graph


def test_exchange_preview_marks_exchange_red_and_endpoints_affected() -> None:
    model, ids, (source, target, key) = sample_model()

    preview = build_edge_deletion_preview(model, source, target, key)

    assert preview["target"]["kind"] == "edge"
    assert preview["target"]["type"] == "OPERATIONAL_EXCHANGE"
    assert preview["target_edges"][0]["name"] == "Threat Information"
    assert ids["detect"] in preview["impact_node_ids"]
    assert ids["assess"] in preview["impact_node_ids"]
    assert any(edge["type"] == "COMMUNICATION_MEAN" for edge in preview["impact_edges"])
    assert model.graph.has_edge(source, target, key)


def test_confirmed_exchange_delete_scrubs_communication_reference_only() -> None:
    model, ids, (source, target, key) = sample_model()

    delete_edge(model, source, target, key)

    assert not model.graph.has_edge(source, target, key)
    communication_edges = [
        data
        for _source, _target, _key, data in model.graph.edges(keys=True, data=True)
        if data.get("type") == "COMMUNICATION_MEAN"
    ]
    assert len(communication_edges) == 1
    assert communication_edges[0].get("exchange_refs") == []
    assert ids["detect"] in model.graph
    assert ids["assess"] in model.graph


def test_characteristic_preview_and_delete_keep_owner() -> None:
    model, ids, _exchange = sample_model()
    assert model.add_characteristic(
        ids["detect"],
        {"name": "Latency", "value_type": "number", "value": 2, "unit": "s"},
    )[0]
    target = {
        "kind": "node",
        "node_id": ids["detect"],
        "label": "Detect Threat",
    }
    characteristic = model.characteristics_for_node(ids["detect"])[0]

    preview = build_characteristic_deletion_preview(model, target, 0, characteristic)
    assert preview["target"]["kind"] == "characteristic"
    assert preview["target"]["name"] == "Latency"
    assert ids["detect"] in preview["impact_node_ids"]
    assert model.characteristics_for_node(ids["detect"])

    delete_characteristic(model, target, 0)
    assert ids["detect"] in model.graph
    assert model.characteristics_for_node(ids["detect"]) == []
