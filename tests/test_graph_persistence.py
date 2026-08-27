from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import networkx as nx
import pytest
from networkx.readwrite import json_graph

from graph_model import MODEL_SCHEMA_VERSION, OAGraph


def assert_uuid(value: str) -> None:
    assert str(UUID(value)) == value


def build_model() -> OAGraph:
    model = OAGraph()
    ok, actor, _ = model.add_node(
        "OperationalActor",
        "Operations Coordinator",
        sid="OA-ACTOR-001",
    )
    assert ok
    ok, action, _ = model.add_node(
        "OperationalActivity",
        "Coordinate response",
    )
    assert ok
    ok, message = model.add_relation(actor, "PERFORMS", action)
    assert ok, message
    return model


def test_new_elements_and_relations_use_uuid_identity() -> None:
    model = build_model()
    for node_id, data in model.graph.nodes(data=True):
        assert_uuid(node_id)
        assert data["uuid"] == node_id

    for _, _, data in model.graph.edges(data=True):
        assert_uuid(data["uuid"])


def test_sid_is_optional_and_immutable() -> None:
    model = build_model()
    actor = model.nodes_of_type("OperationalActor")[0]
    assert model.graph.nodes[actor]["sid"] == "OA-ACTOR-001"
    assert not model.update_node_attributes(actor, sid="OA-ACTOR-999")
    assert model.graph.nodes[actor]["sid"] == "OA-ACTOR-001"


def test_atomic_save_and_round_trip(tmp_path: Path) -> None:
    model = build_model()
    path = model.save(tmp_path / "oa_model.json")
    assert path.exists()
    assert not (tmp_path / "oa_model.json.tmp").exists()

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["graph"]["schema_version"] == MODEL_SCHEMA_VERSION
    assert raw["graph"]["identity"] == "uuid"

    loaded = OAGraph.load(path)
    assert loaded.graph.number_of_nodes() == model.graph.number_of_nodes()
    assert loaded.graph.number_of_edges() == model.graph.number_of_edges()
    assert set(loaded.graph.nodes) == set(model.graph.nodes)
    assert not loaded.graph.graph["migrated_from_legacy"]


def test_legacy_migration_requires_explicit_approval(tmp_path: Path) -> None:
    legacy = nx.MultiDiGraph(model="Arcadia Operational Analysis")
    actor = "OperationalActor:operations-coordinator"
    action = "OperationalActivity:coordinate-response"
    legacy.add_node(
        actor,
        type="OperationalActor",
        name="Operations Coordinator",
        expects_activity=True,
        nature="human_individual",
    )
    legacy.add_node(
        action,
        type="OperationalActivity",
        name="Coordinate response",
    )
    legacy.add_edge(actor, action, type="PERFORMS")
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(json_graph.node_link_data(legacy, edges="edges"), indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="allow_migration=True"):
        OAGraph.load(path)

    migrated = OAGraph.load(path, allow_migration=True)
    assert migrated.graph.graph["migrated_from_legacy"]
    assert migrated.graph.number_of_nodes() == 2
    assert migrated.graph.number_of_edges() == 1

    actor_id = migrated.nodes_of_type("OperationalActor")[0]
    action_id = migrated.nodes_of_type("OperationalActivity")[0]
    assert_uuid(actor_id)
    assert_uuid(action_id)
    assert migrated.graph.nodes[actor_id]["sid"] == actor
    assert migrated.graph.nodes[action_id]["sid"] == action
    edge_data = next(iter(migrated.graph.edges(data=True)))[2]
    assert_uuid(edge_data["uuid"])
