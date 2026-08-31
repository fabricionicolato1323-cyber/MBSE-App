from __future__ import annotations

from networkx.readwrite import json_graph

from change_impact_refinement import (
    PRESENTATION_KEY,
    delete_model_node,
    directly_impacted_relations,
    preview_delete_model_node,
    preview_rename_model_node,
    rename_model_node,
    set_change_presentation,
)
from graph_model import OAGraph
from model_io import prepare_model_export
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


def test_rename_preview_does_not_mutate_before_confirmation() -> None:
    model, actor, action, goal = _model()

    ok, error, preview = preview_rename_model_node(
        model,
        action,
        "Detect incoming threats updated",
    )

    assert ok, error
    assert model.name(action) == "Detect incoming threats"
    assert preview["operation"] == "rename_preview"
    assert preview["modified"][0]["old_name"] == "Detect incoming threats"
    assert preview["modified"][0]["name"] == "Detect incoming threats updated"
    assert preview["preview_node_names"] == {action: "Detect incoming threats updated"}
    assert set(preview["impacted_ids"]) == {actor, goal}


def test_confirmed_rename_preserves_stable_id_and_marks_direct_impact() -> None:
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


def test_confirmed_rename_updates_only_name_caches_proven_by_matching_id() -> None:
    model, actor, action, _goal = _model()
    model.graph.graph["reference_cache"] = {
        "activity_id": action,
        "activity_name": "Detect incoming threats",
        "free_text": "Detect incoming threats",
    }
    ok, context, error = model.add_node(
        "OperationalEntity",
        "Operations center",
        nature="infrastructure_or_facility",
        expects_activity=False,
    )
    assert ok, error
    ok, error = model.add_relation(
        actor,
        "COMMUNICATION_MEAN",
        context,
        name="Radio",
        exchange_refs=[
            {
                "source_activity_id": action,
                "source_activity_name": "Detect incoming threats",
                "target_activity_id": action,
                "target_activity_name": "Detect incoming threats",
            }
        ],
    )
    assert ok, error

    ok, error, presentation = rename_model_node(
        model,
        action,
        "Detect incoming threats updated",
    )

    assert ok, error
    cache = model.graph.graph["reference_cache"]
    assert cache["activity_name"] == "Detect incoming threats updated"
    assert cache["free_text"] == "Detect incoming threats"
    communication = next(
        data
        for _source, _target, data in model.graph.edges(data=True)
        if data.get("type") == "COMMUNICATION_MEAN"
    )
    ref = communication["exchange_refs"][0]
    assert ref["source_activity_name"] == "Detect incoming threats updated"
    assert ref["target_activity_name"] == "Detect incoming threats updated"
    assert presentation["propagated_name_copies"] == 3


def test_nonincident_relation_with_explicit_id_reference_is_impacted() -> None:
    model, actor, action, _goal = _model()
    ok, context, error = model.add_node(
        "OperationalEntity",
        "Operations center",
        nature="infrastructure_or_facility",
        expects_activity=False,
    )
    assert ok, error
    ok, error = model.add_relation(
        actor,
        "COMMUNICATION_MEAN",
        context,
        name="Radio",
        exchange_refs=[
            {
                "source_activity_id": action,
                "target_activity_id": "another-action",
                "exchange_name": "Threat report",
            }
        ],
    )
    assert ok, error

    relations = directly_impacted_relations(model, action)

    assert any(item["type"] == "COMMUNICATION_MEAN" and item["name"] == "Radio" for item in relations)
    assert any(item["type"] == "PERFORMS" for item in relations)
    assert any(item["type"] == "SUPPORTS_CAPABILITY" for item in relations)


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
    assert {item["type"] for item in preview["impacted_relations"]} >= {
        "PERFORMS",
        "SUPPORTS_CAPABILITY",
    }

    ok, error, deleted = delete_model_node(model, action)
    assert ok, error
    assert action not in model.graph
    assert actor in model.graph
    assert goal in model.graph
    assert deleted["operation"] == "delete"
    assert set(deleted["impacted_ids"]) == {actor, goal}


def test_presentation_metadata_does_not_change_level1_digest_or_saved_model() -> None:
    model, actor, action, goal = _model()
    before = level1_snapshot_digest(_payload(model), [])

    set_change_presentation(
        model,
        operation="rename_preview",
        modified=[
            {
                "id": action,
                "name": "Detect incoming threats updated",
                "old_name": model.name(action),
                "type": "OperationalActivity",
            }
        ],
        impacted_ids=[actor, goal],
    )
    payload = _payload(model)
    after = level1_snapshot_digest(payload, [])
    exported = prepare_model_export(payload, "Impact test")

    assert before == after
    assert PRESENTATION_KEY not in exported["graph"]
