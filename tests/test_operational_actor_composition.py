from participant_composition import (
    install_operational_actor_composition_support,
)
from graph_model import OAGraph


def _add(graph: OAGraph, node_type: str, name: str) -> str:
    ok, node_id, error = graph.add_node(node_type, name)
    assert ok, error
    return node_id


def test_actor_can_contain_actor_but_not_entity():
    install_operational_actor_composition_support()
    graph = OAGraph()
    parent = _add(graph, "OperationalActor", "Parent role")
    child = _add(graph, "OperationalActor", "Nested role")
    entity = _add(graph, "OperationalEntity", "External group")

    ok, error = graph.add_relation(parent, "CONTAINS", child)
    assert ok, error
    assert graph.structural_parent(child) == parent
    assert graph.decomposition_children(parent) == [child]
    edge_data = next(
        data
        for _, target, data in graph.graph.out_edges(parent, data=True)
        if target == child and data.get("type") == "CONTAINS"
    )
    assert edge_data.get("application_only") is True

    ok, error = graph.add_relation(parent, "CONTAINS", entity)
    assert not ok
    assert "not allowed" in error.lower()


def test_entity_can_still_contain_actor_and_entity():
    install_operational_actor_composition_support()
    graph = OAGraph()
    entity = _add(graph, "OperationalEntity", "Container")
    child_entity = _add(graph, "OperationalEntity", "Nested entity")
    actor = _add(graph, "OperationalActor", "Nested actor")

    assert graph.add_relation(entity, "CONTAINS", child_entity)[0]
    assert graph.add_relation(entity, "CONTAINS", actor)[0]
    assert not graph.decomposition_issues()


def test_actor_to_actor_composition_is_reported_as_valid_decomposition():
    install_operational_actor_composition_support()
    graph = OAGraph()
    parent = _add(graph, "OperationalActor", "Lead role")
    child = _add(graph, "OperationalActor", "Supporting role")
    assert graph.add_relation(parent, "CONTAINS", child)[0]

    assert (parent, child, "CONTAINS") in graph.decomposition_relations()
    assert not graph.decomposition_issues()
