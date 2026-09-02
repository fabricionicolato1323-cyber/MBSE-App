from __future__ import annotations

import copy

from exchange_transport import relationship_identity, resolve_exchange_transport
from sam_connection import SamSettings
from sam_level1_incremental import (
    TRANSPORT_OWNERSHIP_REVISION,
    _edge_fingerprint,
    _legacy_other_edge_fingerprint,
    _scenario_fingerprint,
    build_incremental_plan,
)
from sam_level1_sync import level1_snapshot_digest
from sysml_v2 import generate_sysml_v2


def _model(*, assigned: bool = True) -> dict:
    exchange = {
        "type": "OPERATIONAL_EXCHANGE",
        "source": "activity-source",
        "target": "activity-target",
        "key": 0,
        "name": "Kill count",
        "communication_assignment": "assigned" if assigned else "none",
    }
    communication = {
        "type": "COMMUNICATION_MEAN",
        "source": "entity-a",
        "target": "entity-b",
        "key": 0,
        "name": "Radio link",
        "exchange_refs": [
            {
                "source_activity_id": "activity-source",
                "target_activity_id": "activity-target",
                "exchange_name": "Kill count",
            }
        ] if assigned else [],
    }
    return {
        "graph": {"model_name": "Transport ownership test"},
        "nodes": [
            {"id": "entity-a", "type": "OperationalEntity", "name": "Entity A"},
            {"id": "entity-b", "type": "OperationalEntity", "name": "Entity B"},
            {"id": "activity-source", "type": "OperationalActivity", "name": "Source activity"},
            {"id": "activity-target", "type": "OperationalActivity", "name": "Target activity"},
        ],
        "edges": [communication, exchange],
        "scenarios": [],
    }


def _legacy_model() -> dict:
    model = _model(assigned=True)
    exchange = next(edge for edge in model["edges"] if edge["type"] == "OPERATIONAL_EXCHANGE")
    communication = next(edge for edge in model["edges"] if edge["type"] == "COMMUNICATION_MEAN")
    exchange.pop("communication_assignment", None)
    communication.pop("exchange_refs", None)
    model["edges"].extend(
        [
            {"type": "PERFORMS", "source": "entity-a", "target": "activity-source", "key": 0},
            {"type": "PERFORMS", "source": "entity-b", "target": "activity-target", "key": 0},
        ]
    )
    return model


def _settings() -> SamSettings:
    return SamSettings(
        server_url="https://sam.invalid",
        organization_id="org",
        project_id="project",
        access_token="token",
    )


def test_resolver_returns_communication_mean_only_for_assigned_exchange():
    model = _model(assigned=True)
    exchange = next(edge for edge in model["edges"] if edge["type"] == "OPERATIONAL_EXCHANGE")
    medium = resolve_exchange_transport(model["edges"], exchange)
    assert medium is not None
    assert medium["name"] == "Radio link"

    unassigned = _model(assigned=False)
    exchange = next(edge for edge in unassigned["edges"] if edge["type"] == "OPERATIONAL_EXCHANGE")
    assert resolve_exchange_transport(unassigned["edges"], exchange) is None


def test_legacy_single_medium_matches_diagram_and_sysml_ownership():
    model = _legacy_model()
    exchange = next(edge for edge in model["edges"] if edge["type"] == "OPERATIONAL_EXCHANGE")

    medium = resolve_exchange_transport(model["edges"], exchange)
    assert medium is not None
    assert medium["name"] == "Radio link"

    text = generate_sysml_v2(model)
    connection = "connection oa_communication_Radio_link : CommunicationMean"
    flow = "flow oa_exchange_Kill_count : OperationalExchange"
    assert text.count(flow) == 1
    assert text.index(connection) < text.index(flow)
    assert "connect oa_entity_Entity_A to oa_entity_Entity_B {" in text


def test_legacy_transport_is_not_guessed_when_two_media_match():
    model = _legacy_model()
    model["edges"].append(
        {
            "type": "COMMUNICATION_MEAN",
            "source": "entity-a",
            "target": "entity-b",
            "key": 1,
            "name": "Backup link",
        }
    )
    exchange = next(edge for edge in model["edges"] if edge["type"] == "OPERATIONAL_EXCHANGE")
    assert resolve_exchange_transport(model["edges"], exchange) is None


def test_sysml_nests_assigned_flow_usage_inside_communication_mean_usage():
    text = generate_sysml_v2(_model(assigned=True))
    connection = "connection oa_communication_Radio_link : CommunicationMean"
    flow = "flow oa_exchange_Kill_count : OperationalExchange"

    assert connection in text
    assert flow in text
    assert text.count(flow) == 1
    assert text.index(connection) < text.index(flow)
    assert "connect oa_entity_Entity_A to oa_entity_Entity_B {" in text
    assert "from oa_operationalBehavior.oa_activity_Source_activity" in text
    assert "to oa_operationalBehavior.oa_activity_Target_activity" in text


def test_sysml_keeps_unassigned_flow_usage_in_operational_behavior():
    text = generate_sysml_v2(_model(assigned=False))
    connection = "connection oa_communication_Radio_link : CommunicationMean"
    flow = "flow oa_exchange_Kill_count : OperationalExchange"

    assert text.count(flow) == 1
    assert text.index(flow) < text.index(connection)
    assert "connect oa_entity_Entity_A to oa_entity_Entity_B;" in text


def test_existing_v2_manifest_detects_one_time_owner_move_even_when_digest_is_unchanged():
    model = _model(assigned=True)
    exchange = next(edge for edge in model["edges"] if edge["type"] == "OPERATIONAL_EXCHANGE")
    relationship_id = relationship_identity(exchange)
    digest = level1_snapshot_digest(model, [])

    model["graph"]["sam_sync"] = {
        "version": 2,
        "project_id": "project",
        "instance_package_name": "MBSE_Instance_test",
        "instance_package_id": "pkg-1",
        "snapshot_digest": digest,
        "nodes": {
            node["id"]: {
                "sam_id": f"sam-{node['id']}",
                "type": node["type"],
                "name": node["name"],
                "source": copy.deepcopy(node),
            }
            for node in model["nodes"]
        },
        "relationships": {
            relationship_id: {
                "sam_id": "sam-flow-1",
                "type": "OPERATIONAL_EXCHANGE",
                "source_id": exchange["source"],
                "target_id": exchange["target"],
                "key": 0,
                "name": exchange["name"],
                "source": copy.deepcopy(exchange),
            }
        },
        "relationship_tracking_complete": True,
        "other_edges_fingerprint": _legacy_other_edge_fingerprint(model),
        "edges_fingerprint": _edge_fingerprint(model),
        "scenarios_fingerprint": _scenario_fingerprint([]),
    }

    plan = build_incremental_plan(model, scenarios=[], settings=_settings())

    assert plan["supported"] is True
    assert plan["mode"] == "incremental_change_set"
    assert plan["relationship_counts"]["update"] == 1
    update = plan["relationship_updates"][0]
    assert update["owner_changed"] is True
    assert update["old_owner_kind"] == "behavior"
    assert update["new_owner_kind"] == "communication_mean"
    assert update["new_owner_name"] == "Radio link"


def test_current_transport_revision_allows_digest_noop():
    model = _model(assigned=True)
    exchange = next(edge for edge in model["edges"] if edge["type"] == "OPERATIONAL_EXCHANGE")
    relationship_id = relationship_identity(exchange)
    digest = level1_snapshot_digest(model, [])
    medium = resolve_exchange_transport(model["edges"], exchange)
    assert medium is not None

    model["graph"]["sam_sync"] = {
        "version": 2,
        "transport_ownership_revision": TRANSPORT_OWNERSHIP_REVISION,
        "project_id": "project",
        "instance_package_name": "MBSE_Instance_test",
        "instance_package_id": "pkg-1",
        "snapshot_digest": digest,
        "nodes": {},
        "relationships": {
            relationship_id: {
                "sam_id": "sam-flow-2",
                "type": "OPERATIONAL_EXCHANGE",
                "source_id": exchange["source"],
                "target_id": exchange["target"],
                "key": 0,
                "name": exchange["name"],
                "source": copy.deepcopy(exchange),
                "owner_kind": "communication_mean",
                "owner_relationship_id": relationship_identity(medium),
                "owner_name": "Radio link",
            }
        },
    }

    plan = build_incremental_plan(model, scenarios=[], settings=_settings())
    assert plan["mode"] == "incremental_noop"
    assert plan["relationship_counts"]["update"] == 0
