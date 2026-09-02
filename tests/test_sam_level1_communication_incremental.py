from __future__ import annotations

import copy

from exchange_transport import relationship_identity
from sam_level1_communication_incremental import (
    COMMUNICATION_TRACKING_REVISION,
    _communication_change_set,
    _communication_source,
    _communication_tracking_migration_is_proven,
    _unhandled_edge_fingerprint,
)
from sam_level1_incremental import (
    _edge_fingerprint,
    _legacy_other_edge_fingerprint,
)


def _model(*, assigned: bool) -> dict:
    exchange = {
        "type": "OPERATIONAL_EXCHANGE",
        "source": "activity-source",
        "target": "activity-target",
        "key": 0,
        "name": "Threat location",
        "communication_assignment": "assigned" if assigned else "none",
    }
    communication = {
        "type": "COMMUNICATION_MEAN",
        "source": "entity-a",
        "target": "entity-b",
        "key": 0,
        "name": "Radio link",
        "exchange_refs": (
            [{
                "source_activity_id": "activity-source",
                "target_activity_id": "activity-target",
                "exchange_name": "Threat location",
            }]
            if assigned
            else []
        ),
    }
    return {
        "nodes": [
            {"id": "entity-a", "type": "OperationalEntity", "name": "Entity A"},
            {"id": "entity-b", "type": "OperationalEntity", "name": "Entity B"},
            {"id": "activity-source", "type": "OperationalActivity", "name": "Source activity"},
            {"id": "activity-target", "type": "OperationalActivity", "name": "Target activity"},
        ],
        "edges": [
            {"type": "PERFORMS", "source": "entity-a", "target": "activity-source", "key": 0},
            {"type": "PERFORMS", "source": "entity-b", "target": "activity-target", "key": 0},
            communication,
            exchange,
        ],
        "scenarios": [],
    }


def _old_state(model: dict) -> dict:
    exchange = next(
        edge for edge in model["edges"] if edge["type"] == "OPERATIONAL_EXCHANGE"
    )
    return {
        "version": 2,
        "project_id": "project",
        "other_edges_fingerprint": _legacy_other_edge_fingerprint(model),
        "edges_fingerprint": _edge_fingerprint(model),
        "relationships": {
            relationship_identity(exchange): {
                "sam_id": "sam-flow",
                "type": "OPERATIONAL_EXCHANGE",
                "name": exchange["name"],
                "source": copy.deepcopy(exchange),
                "owner_kind": "behavior",
                "owner_relationship_id": None,
                "owner_name": "oa_operationalBehavior",
            }
        },
    }


def _tracked_state(model: dict) -> dict:
    state = _old_state(model)
    communication = next(
        edge for edge in model["edges"] if edge["type"] == "COMMUNICATION_MEAN"
    )
    state["communication_tracking_revision"] = COMMUNICATION_TRACKING_REVISION
    state["unhandled_edges_fingerprint"] = _unhandled_edge_fingerprint(model)
    state["communication_means"] = {
        relationship_identity(communication): {
            "sam_id": "sam-radio",
            "type": "COMMUNICATION_MEAN",
            "source_id": communication["source"],
            "target_id": communication["target"],
            "key": communication.get("key", 0),
            "name": communication["name"],
            "source": _communication_source(communication),
        }
    }
    return state


def test_exchange_refs_only_is_safe_old_manifest_migration():
    baseline = _model(assigned=False)
    current = _model(assigned=True)
    assert _communication_tracking_migration_is_proven(current, _old_state(baseline))


def test_unrelated_performs_change_is_not_hidden_by_migration():
    baseline = _model(assigned=False)
    current = _model(assigned=True)
    current["edges"][0]["source"] = "different-performer"
    assert not _communication_tracking_migration_is_proven(current, _old_state(baseline))


def test_exchange_refs_do_not_update_communication_mean():
    baseline = _model(assigned=False)
    current = _model(assigned=True)
    delta = _communication_change_set(current, _tracked_state(baseline))
    assert delta["counts"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
        "unchanged": 1,
    }


def test_communication_mean_create_and_delete_are_detected():
    baseline = _model(assigned=False)
    tracked = _tracked_state(baseline)

    no_medium = copy.deepcopy(baseline)
    no_medium["edges"] = [
        edge for edge in no_medium["edges"] if edge["type"] != "COMMUNICATION_MEAN"
    ]
    deleted = _communication_change_set(no_medium, tracked)
    assert deleted["counts"]["delete"] == 1

    empty_state = copy.deepcopy(tracked)
    empty_state["communication_means"] = {}
    created = _communication_change_set(baseline, empty_state)
    assert created["counts"]["create"] == 1


def test_communication_mean_rename_is_name_only_update():
    baseline = _model(assigned=False)
    renamed = copy.deepcopy(baseline)
    medium = next(edge for edge in renamed["edges"] if edge["type"] == "COMMUNICATION_MEAN")
    medium["name"] = "Tactical radio"

    delta = _communication_change_set(renamed, _tracked_state(baseline))
    assert delta["counts"]["update"] == 1
    assert delta["update"][0]["old_name"] == "Radio link"
    assert delta["update"][0]["new_name"] == "Tactical radio"
