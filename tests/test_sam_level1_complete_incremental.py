from __future__ import annotations

import copy

from sam_level1_complete_incremental import (
    SCENARIO_STRUCTURE_REVISION,
    _fingerprint,
    _record,
    _shadow_for_complete_plan,
    _strategy,
    relationship_identity,
    remaining_relationship_change_set,
)


def _model():
    return {
        "nodes": [
            {"id": "entity", "type": "OperationalEntity", "name": "Area"},
            {"id": "actor", "type": "OperationalActor", "name": "Operator"},
            {"id": "activity", "type": "OperationalActivity", "name": "Monitor"},
            {"id": "capability", "type": "OperationalCapability", "name": "Protect area"},
        ],
        "edges": [
            {"type": "CONTAINS", "source": "entity", "target": "actor", "key": 0},
            {"type": "PERFORMS", "source": "actor", "target": "activity", "key": 0},
            {
                "type": "SUPPORTS_CAPABILITY",
                "source": "activity",
                "target": "capability",
                "key": 0,
            },
            {"type": "LOCATED_IN", "source": "actor", "target": "entity", "key": 0},
        ],
    }


def _state(model):
    records = {}
    for index, edge in enumerate(model["edges"], start=1):
        identity = relationship_identity(edge)
        records[identity] = _record(
            edge,
            None if _strategy(edge) == "nested_usage" else f"sam-rel-{index}",
        )
    return {
        "nodes": {
            node["id"]: {
                "sam_id": f"sam-{node['id']}",
                "source": copy.deepcopy(node),
            }
            for node in model["nodes"]
        },
        "remaining_relationships": records,
        "complete_relationship_tracking_revision": 1,
        "scenario_structure_revision": SCENARIO_STRUCTURE_REVISION,
        "unhandled_edges_fingerprint": _fingerprint(model),
    }


def test_remaining_relationship_baseline_is_noop():
    model = _model()
    delta = remaining_relationship_change_set(model, _state(model))
    assert delta["counts"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
        "unchanged": 4,
    }


def test_remaining_relationship_create_update_delete_are_detected():
    model = _model()
    state = _state(model)
    changed = copy.deepcopy(model)

    changed["edges"].pop()  # delete LOCATED_IN
    changed["edges"][1]["name"] = "performs monitoring"
    changed["nodes"].append(
        {"id": "activity-child", "type": "OperationalActivity", "name": "Inspect"}
    )
    changed["edges"].append(
        {
            "type": "DECOMPOSES",
            "source": "activity",
            "target": "activity-child",
            "key": 0,
        }
    )

    delta = remaining_relationship_change_set(changed, state)
    assert delta["counts"]["create"] == 1
    assert delta["counts"]["update"] == 1
    assert delta["counts"]["delete"] == 1
    assert delta["update"][0]["new_name"] == "performs monitoring"


def test_old_activity_only_scenario_tree_is_forced_to_replace_once():
    model = _model()
    state = _state(model)
    state["scenario_structure_revision"] = 0
    state["scenarios"] = {
        "id:scenario-1": {
            "sam_id": "sam-scenario-1",
            "source": {
                "id": "scenario-1",
                "name": "Patrol",
                "steps": [],
            },
        }
    }
    shadow = _shadow_for_complete_plan(
        {**model, "graph": {"sam_sync": state}},
        state,
    )
    assert (
        shadow["graph"]["sam_sync"]["scenarios"]["id:scenario-1"]["source"][
            "__sam_structure_revision"
        ]
        == 0
    )

    state["scenario_structure_revision"] = SCENARIO_STRUCTURE_REVISION
    shadow = _shadow_for_complete_plan(
        {**model, "graph": {"sam_sync": state}},
        state,
    )
    assert (
        "__sam_structure_revision"
        not in shadow["graph"]["sam_sync"]["scenarios"]["id:scenario-1"]["source"]
    )
