from __future__ import annotations

from networkx.readwrite import json_graph

from change_impact_refinement import (
    PRESENTATION_KEY,
    delete_model_node,
    preview_delete_model_node,
    rename_model_node,
    set_change_presentation,
)
from graph_model import OAGraph
from sam_level1_sync import level1_snapshot_digest


def _model() -> tuple[OAGraph, str, str, str]:
    model = OAGraph()
    ok, actor, error = model.add_node(
        "OperationalActor",
        "Threat detection system",
        nature="human_individual",
    )
    assert ok, error
    ok, action, error = model.add_node("OperationalActivity", "Detect incoming threats")
    assert ok, error
    ok, goal, error = model.add_node("OperationalCapability", "Protect target area")
    assert ok, error
    ok, error = model.add_relation(actor, "PERFORMS", action)
    assert ok, error
    ok, error = model.add_relation(action, "SUPPORTS_CAPABILITY", goal)
    assert ok, error
    return model, actor, action, goal


def _payload(model: OAGraph) -> dict:
    return json_graph.node_link_data(model.graph, edges="edges")


def test_rename_preserves_stable_id_and_marks_direct_impact() -> None:
    model, actor, action, goal = _model()

    ok, error, presentation = rename_model_node(
        model,
        action,
        "Detect incoming threats updated",
    )

    assert ok, error
    assert action in model.graph
    assert model.name(action) == "Detect incoming threats updated"
    assert presentation["modified_ids"] == [action]
    assert set(presentation["impacted_ids"]) == {actor, goal}
    assert model.graph.graph[PRESENTATION_KEY]["operation"] == "rename"


def test_rename_rejects_duplicate_without_mutating_model() -> None:
    model, _actor, action, _goal = _model()
    ok, other, error = model.add_node("OperationalActivity", "Track threats")
    assert ok, error

    ok, error, presentation = rename_model_node(model, action, "Track threats")

    assert not ok
    assert "already used" in error
    assert presentation == {}
    assert model.name(action) == "Detect incoming threats"
    assert model.name(other) == "Track threats"


def test_delete_preview_keeps_target_and_delete_removes_only_target() -> None:
    model, actor, action, goal = _model()

    preview = preview_delete_model_node(model, action)
    assert action in model.graph
    assert preview["operation"] == "delete_preview"
    assert preview["modified_ids"] == [action]
    assert set(preview["impacted_ids"]) == {actor, goal}

    ok, error, deleted = delete_model_node(model, action)
    assert ok, error
    assert action not in model.graph
    assert actor in model.graph
    assert goal in model.graph
    assert deleted["operation"] == "delete"
    assert set(deleted["impacted_ids"]) == {actor, goal}


def test_presentation_metadata_does_not_change_level1_digest() -> None:
    model, actor, action, goal = _model()
    before = level1_snapshot_digest(_payload(model), [])

    set_change_presentation(
        model,
        operation="rename",
        modified=[{"id": action, "name": model.name(action), "type": "OperationalActivity"}],
        impacted_ids=[actor, goal],
    )
    after = level1_snapshot_digest(_payload(model), [])

    assert before == after
