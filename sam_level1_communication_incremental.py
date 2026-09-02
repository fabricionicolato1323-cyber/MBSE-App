"""Incremental Communication Mean support layered on Level 1C flow sync."""
from __future__ import annotations

import copy
from time import perf_counter
from typing import Any
from uuid import uuid4

from exchange_transport import relationship_identity
from sam_connection import SamSettings
from sam_level1_direct import _MetadataTolerantFactory
from sam_level1_incremental import (
    SYNC_STATE_VERSION,
    TRANSPORT_OWNERSHIP_REVISION,
    _delete_owned_tree,
    _descendants,
    _edge_fingerprint,
    _legacy_other_edge_fingerprint,
    _managed_instance,
    _nodes_by_id,
    _other_edge_fingerprint,
    _relationship_endpoint_ids,
    _relationship_name,
    _rows,
    _scenario_fingerprint,
    build_incremental_plan,
    sync_level1_incremental,
)
from sam_level1_managed_direct import _library_status
from sam_level1_sync import SamLevel1SyncError, _documentation, _source_document
from sam_level1_transactional import _element_id, _element_name, _load_project
from sam_reload_safe_factory import ReloadSafeFactory

COMMUNICATION_TRACKING_REVISION = 1


def _communication_source(edge: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(edge)
    value.pop("exchange_refs", None)
    return value


def _communication_edges_by_id(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for edge in _rows(model.get("edges")):
        if str(edge.get("type") or "") != "COMMUNICATION_MEAN":
            continue
        identity = relationship_identity(edge)
        if identity in result:
            raise SamLevel1SyncError(
                f"Communication Mean identity {identity!r} is duplicated in the local model."
            )
        result[identity] = copy.deepcopy(edge)
    return result


def _unhandled_edge_fingerprint(model: dict[str, Any]) -> str:
    shadow = {
        "edges": [
            copy.deepcopy(edge)
            for edge in _rows(model.get("edges"))
            if str(edge.get("type") or "")
            not in {"OPERATIONAL_EXCHANGE", "COMMUNICATION_MEAN"}
        ]
    }
    return _edge_fingerprint(shadow)


def _communication_tracking_migration_is_proven(
    model: dict[str, Any], state: dict[str, Any]
) -> bool:
    """Accept an old v2 manifest only when the mismatch is carrier metadata."""
    previous_other = state.get("other_edges_fingerprint")
    if _legacy_other_edge_fingerprint(model) == previous_other:
        return True
    if _other_edge_fingerprint(model) == previous_other:
        return True

    previous = state.get("relationships")
    previous = previous if isinstance(previous, dict) else {}
    old_flows = [
        copy.deepcopy(record["source"])
        for record in previous.values()
        if isinstance(record, dict)
        and record.get("type") == "OPERATIONAL_EXCHANGE"
        and isinstance(record.get("source"), dict)
    ]
    candidate = copy.deepcopy(model)
    candidate["edges"] = [
        copy.deepcopy(edge)
        for edge in _rows(model.get("edges"))
        if str(edge.get("type") or "") != "OPERATIONAL_EXCHANGE"
    ] + old_flows
    if _edge_fingerprint(candidate) == state.get("edges_fingerprint"):
        return True

    for mode in ("missing", "empty"):
        compat = copy.deepcopy(candidate)
        for edge in _rows(compat.get("edges")):
            if str(edge.get("type") or "") != "COMMUNICATION_MEAN":
                continue
            if mode == "missing":
                edge.pop("exchange_refs", None)
            else:
                edge["exchange_refs"] = []
        if _edge_fingerprint(compat) == state.get("edges_fingerprint"):
            return True
    return False


def _communication_record(edge: dict[str, Any], sam_id: str) -> dict[str, Any]:
    return {
        "sam_id": sam_id,
        "type": "COMMUNICATION_MEAN",
        "source_id": str(edge.get("source") or ""),
        "target_id": str(edge.get("target") or ""),
        "key": edge.get("key", 0),
        "name": _relationship_name(edge),
        "source": _communication_source(edge),
    }


def enrich_state_with_current_communication_means(
    model: dict[str, Any],
    *,
    scenarios: list[dict[str, Any]],
    state: dict[str, Any],
    settings: SamSettings,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
    require_migration_proof: bool = True,
) -> dict[str, Any]:
    """Read-only one-time adoption of Communication Mean SAM IDs."""
    if int(state.get("communication_tracking_revision", 0) or 0) == COMMUNICATION_TRACKING_REVISION:
        return copy.deepcopy(state)
    if int(state.get("version", 0) or 0) != SYNC_STATE_VERSION:
        raise SamLevel1SyncError("Communication Mean tracking requires a v2 manifest.")
    if _scenario_fingerprint(scenarios) != state.get("scenarios_fingerprint"):
        raise SamLevel1SyncError(
            "Operational Scenarios changed during Communication Mean tracking migration."
        )
    if require_migration_proof and not _communication_tracking_migration_is_proven(model, state):
        raise SamLevel1SyncError(
            "The old manifest cannot prove that the non-flow delta is only Communication "
            "Mean transport metadata. No SAM data was changed."
        )

    _, _, project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    package = _managed_instance(project, state)
    descendants = _descendants(project, package)
    records: dict[str, dict[str, Any]] = {}
    for identity, edge in _communication_edges_by_id(model).items():
        name = _relationship_name(edge)
        matches = [item for item in descendants if _element_name(item) == name]
        if len(matches) != 1:
            raise SamLevel1SyncError(
                f"Cannot adopt Communication Mean {name!r}: found {len(matches)} SAM matches."
            )
        sam_id = _element_id(matches[0])
        if not sam_id:
            raise SamLevel1SyncError(f"Communication Mean {name!r} has no stable SAM ID.")
        records[identity] = _communication_record(edge, sam_id)

    migrated = copy.deepcopy(state)
    migrated["communication_means"] = records
    migrated["communication_tracking_revision"] = COMMUNICATION_TRACKING_REVISION
    migrated["unhandled_edges_fingerprint"] = _unhandled_edge_fingerprint(model)
    migrated["other_edges_fingerprint"] = _other_edge_fingerprint(model)
    return migrated


def _communication_change_set(
    model: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    current = _communication_edges_by_id(model)
    previous = state.get("communication_means")
    previous = previous if isinstance(previous, dict) else {}
    current_ids, previous_ids = set(current), set(previous)

    creates = [
        {"relationship_id": rid, "edge": copy.deepcopy(current[rid])}
        for rid in sorted(current_ids - previous_ids)
    ]
    deletes = [
        {
            "relationship_id": rid,
            "sam_id": (previous.get(rid) or {}).get("sam_id"),
            "old_name": str((previous.get(rid) or {}).get("name") or ""),
            "edge": copy.deepcopy((previous.get(rid) or {}).get("source") or {}),
        }
        for rid in sorted(previous_ids - current_ids)
    ]
    updates: list[dict[str, Any]] = []
    unchanged = 0
    for rid in sorted(current_ids & previous_ids):
        record = previous.get(rid) if isinstance(previous.get(rid), dict) else {}
        old = record.get("source") if isinstance(record.get("source"), dict) else {}
        new = _communication_source(current[rid])
        if old == new:
            unchanged += 1
            continue
        old_without_name, new_without_name = copy.deepcopy(old), copy.deepcopy(new)
        old_without_name.pop("name", None)
        new_without_name.pop("name", None)
        if old_without_name != new_without_name:
            raise SamLevel1SyncError(
                f"Communication Mean {_relationship_name(new)!r} changed non-name properties "
                "without changing its structural identity."
            )
        updates.append(
            {
                "relationship_id": rid,
                "sam_id": record.get("sam_id"),
                "old_name": str(record.get("name") or _relationship_name(old)),
                "new_name": _relationship_name(new),
                "old_edge": copy.deepcopy(old),
                "edge": copy.deepcopy(current[rid]),
            }
        )
    return {
        "create": creates,
        "update": updates,
        "delete": deletes,
        "unchanged": unchanged,
        "counts": {
            "create": len(creates),
            "update": len(updates),
            "delete": len(deletes),
            "unchanged": unchanged,
        },
    }


def _shadow_model_for_flow_plan(
    model: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    """Neutralize the old generic blocker after independent migration proof."""
    value = copy.deepcopy(model)
    shadow = copy.deepcopy(state)
    shadow["other_edges_fingerprint"] = _other_edge_fingerprint(model)
    if int(shadow.get("transport_ownership_revision", 0) or 0) != TRANSPORT_OWNERSHIP_REVISION:
        shadow["transport_ownership_revision"] = TRANSPORT_OWNERSHIP_REVISION
        shadow["snapshot_digest"] = "__force_transport_owner_review__"
    value.setdefault("graph", {})["sam_sync"] = shadow
    return value


def build_incremental_plan_with_communication(
    model: dict[str, Any],
    *,
    scenarios: list[dict[str, Any]],
    settings: SamSettings,
) -> dict[str, Any]:
    state = model.get("graph", {}).get("sam_sync") if isinstance(model.get("graph"), dict) else None
    if not isinstance(state, dict):
        return build_incremental_plan(model, scenarios=scenarios, settings=settings)

    base = build_incremental_plan(
        _shadow_model_for_flow_plan(model, state),
        scenarios=scenarios,
        settings=settings,
    )
    comm = _communication_change_set(model, state)
    unsupported = list(base.get("unsupported_changes") or [])

    expected_unhandled = state.get("unhandled_edges_fingerprint")
    if expected_unhandled is not None and _unhandled_edge_fingerprint(model) != expected_unhandled:
        unsupported.append(
            "relationship types outside OPERATIONAL_EXCHANGE/COMMUNICATION_MEAN changed; "
            "their incremental handlers are pending"
        )

    previous_flows = state.get("relationships")
    previous_flows = previous_flows if isinstance(previous_flows, dict) else {}
    for item in comm["delete"]:
        rid = str(item.get("relationship_id") or "")
        owned = [
            record.get("name")
            for record in previous_flows.values()
            if isinstance(record, dict)
            and str(record.get("owner_relationship_id") or "") == rid
        ]
        if owned:
            unsupported.append(
                f"Communication Mean {_relationship_name(item.get('edge') or {})!r} still owns "
                f"Operational Exchange(s) {owned!r}; synchronize those flows as unassigned or "
                "moved before deleting the Communication Mean"
            )

    base_rel = base.get("relationship_counts") or {}
    counts = {
        "create": int(base_rel.get("create") or 0) + comm["counts"]["create"],
        "update": int(base_rel.get("update") or 0) + comm["counts"]["update"],
        "delete": int(base_rel.get("delete") or 0) + comm["counts"]["delete"],
        "unchanged": int(base_rel.get("unchanged") or 0) + comm["counts"]["unchanged"],
    }
    creates = list(base.get("relationship_creates") or []) + comm["create"]
    updates = list(base.get("relationship_updates") or []) + comm["update"]
    deletes = list(base.get("relationship_deletes") or []) + comm["delete"]
    has_rel = any(counts[k] for k in ("create", "update", "delete"))
    node_counts = base.get("counts") or {}
    has_nodes = any(int(node_counts.get(k) or 0) for k in ("create", "update", "delete"))

    has_comm = any(comm["counts"][k] for k in ("create", "update", "delete"))
    has_flow = any(int(base_rel.get(k) or 0) for k in ("create", "update", "delete"))
    if has_comm and (has_flow or has_nodes):
        unsupported.append(
            "Communication Mean structural changes must be synchronized separately from "
            "node or Operational Exchange changes in this increment"
        )

    unsupported = list(dict.fromkeys(unsupported))
    result = dict(base)
    result.update(
        {
            "mode": (
                "incremental_noop"
                if not has_rel and not has_nodes and not unsupported
                else "incremental_change_set"
            ),
            "supported": not unsupported,
            "relationship_counts": counts,
            "relationship_creates": creates,
            "relationship_updates": updates,
            "relationship_deletes": deletes,
            "relationship_changes_pending": bool(unsupported),
            "unsupported_changes": unsupported,
        }
    )
    return result


def _communication_only_delta(plan: dict[str, Any]) -> tuple[list, list, list]:
    def pick(items):
        return [
            item
            for item in items
            if isinstance(item.get("edge"), dict)
            and str(item["edge"].get("type") or "") == "COMMUNICATION_MEAN"
        ]
    return (
        pick(plan.get("relationship_creates") or []),
        pick(plan.get("relationship_updates") or []),
        pick(plan.get("relationship_deletes") or []),
    )


def _refresh_tracking_state(
    model: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    value = copy.deepcopy(state)
    value["communication_tracking_revision"] = COMMUNICATION_TRACKING_REVISION
    value["unhandled_edges_fingerprint"] = _unhandled_edge_fingerprint(model)
    value["other_edges_fingerprint"] = _other_edge_fingerprint(model)
    return value


def sync_level1_incremental_with_communication(
    model: dict[str, Any],
    *,
    scenarios: list[dict[str, Any]],
    settings: SamSettings,
    expected_digest: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Delegate flow/node sync to Level 1C; handle Communication Mean-only deltas."""
    started = perf_counter()
    state = model.get("graph", {}).get("sam_sync") if isinstance(model.get("graph"), dict) else None
    if not isinstance(state, dict):
        raise SamLevel1SyncError("Incremental SAM state is missing.")

    plan = build_incremental_plan_with_communication(
        model, scenarios=scenarios, settings=settings
    )
    if expected_digest and expected_digest != plan.get("snapshot_digest"):
        raise SamLevel1SyncError(
            "The model changed after the change set was reviewed. Review it again."
        )
    if not plan.get("supported"):
        raise SamLevel1SyncError(
            "This reviewed Level 1 change set cannot be synchronized yet: "
            + "; ".join(plan.get("unsupported_changes") or [])
        )

    comm_creates, comm_updates, comm_deletes = _communication_only_delta(plan)
    has_comm = bool(comm_creates or comm_updates or comm_deletes)
    if not has_comm:
        shadow = _shadow_model_for_flow_plan(model, state)
        result = sync_level1_incremental(
            shadow,
            scenarios=scenarios,
            settings=settings,
            expected_digest=expected_digest,
            connector_class=connector_class,
            project_manager_class=project_manager_class,
            factory_class=factory_class,
        )
        if isinstance(result.get("sync_state"), dict):
            result["sync_state"] = _refresh_tracking_state(
                model, result["sync_state"]
            )
        return result

    connector, _, project, resolved_factory = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    for item in comm_updates + comm_deletes:
        element = project.find_element_by_id(str(item.get("sam_id") or ""))
        if element is None:
            raise SamLevel1SyncError(
                f"Communication Mean {item.get('relationship_id')!r} no longer exists in SAM."
            )

    package = _managed_instance(project, state)
    structure_matches = [
        item for item in _descendants(project, package)
        if _element_name(item) == "oa_operationalContext"
    ]
    if len(structure_matches) != 1:
        raise SamLevel1SyncError("oa_operationalContext could not be resolved uniquely.")
    structure = structure_matches[0]
    library = _library_status(project)
    if not library.get("loaded"):
        raise SamLevel1SyncError("The reusable ArcadiaOA library is not complete.")
    definition = library["definitions"]["CommunicationMean"]
    raw_factory = resolved_factory(project, connector)
    factory = _MetadataTolerantFactory(ReloadSafeFactory(project, raw_factory))

    nodes = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}
    staged: list[dict[str, Any]] = []
    for item in comm_creates:
        edge = item["edge"]
        source_record = nodes.get(str(edge.get("source") or ""), {})
        target_record = nodes.get(str(edge.get("target") or ""), {})
        source = project.find_element_by_id(str(source_record.get("sam_id") or ""))
        target = project.find_element_by_id(str(target_record.get("sam_id") or ""))
        if source is None or target is None:
            raise SamLevel1SyncError(
                f"Communication Mean {_relationship_name(edge)!r} endpoints are not mapped in SAM."
            )
        staging_name = f"__MBSE_COMM_NEW_{uuid4().hex[:10]}"
        relationship = factory.create_connection_usage(
            name=staging_name,
            owner=structure,
            connection_definition=[definition],
            source=[source],
            target=[target],
            source_feature=source,
            target_feature=[target],
            related_feature=[source, target],
            is_directed=False,
        )
        _documentation(factory, relationship, _source_document(edge, "relationship"))
        staged.append(
            {
                "relationship_id": item["relationship_id"],
                "sam_id": _element_id(relationship),
                "final_name": _relationship_name(edge),
                "source_sam_id": _element_id(source),
                "target_sam_id": _element_id(target),
                "edge": copy.deepcopy(edge),
            }
        )

    project.start_transactional_mode()
    try:
        for item in comm_updates:
            element = project.find_element_by_id(str(item.get("sam_id") or ""))
            element.name = item["new_name"]
        for item in staged:
            element = project.find_element_by_id(str(item.get("sam_id") or ""))
            if element is None:
                raise SamLevel1SyncError("A staged Communication Mean disappeared.")
            element.name = item["final_name"]
        for item in comm_deletes:
            element = project.find_element_by_id(str(item.get("sam_id") or ""))
            _delete_owned_tree(element, project)
        project.stop_transactional_mode()
    except Exception:
        raise

    _, _, verified, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=resolved_factory,
    )
    for item in comm_updates:
        current = verified.find_element_by_id(str(item.get("sam_id") or ""))
        if current is None or _element_name(current) != item["new_name"]:
            raise SamLevel1SyncError("Communication Mean UPDATE verification failed.")
    for item in staged:
        current = verified.find_element_by_id(str(item.get("sam_id") or ""))
        if current is None or _element_name(current) != item["final_name"]:
            raise SamLevel1SyncError("Communication Mean CREATE verification failed.")
        endpoint_ids = _relationship_endpoint_ids(verified, current)
        expected = {str(item["source_sam_id"]), str(item["target_sam_id"])}
        if endpoint_ids and not expected.issubset(endpoint_ids):
            raise SamLevel1SyncError("Communication Mean endpoint verification failed.")
    for item in comm_deletes:
        if verified.find_element_by_id(str(item.get("sam_id") or "")) is not None:
            raise SamLevel1SyncError("Communication Mean DELETE verification failed.")

    new_state = _refresh_tracking_state(model, state)
    records = (
        copy.deepcopy(new_state.get("communication_means"))
        if isinstance(new_state.get("communication_means"), dict)
        else {}
    )
    for item in comm_deletes:
        records.pop(str(item["relationship_id"]), None)
    for item in comm_updates:
        records[str(item["relationship_id"])] = _communication_record(
            item["edge"], str(item["sam_id"])
        )
    for item in staged:
        records[str(item["relationship_id"])] = _communication_record(
            item["edge"], str(item["sam_id"])
        )
    new_state["communication_means"] = records
    new_state["snapshot_digest"] = plan["snapshot_digest"]
    new_state["edges_fingerprint"] = _edge_fingerprint(model)
    new_state["scenarios_fingerprint"] = _scenario_fingerprint(scenarios)

    return {
        "status": "synced",
        "mode": "incremental_change_set",
        "sam_write_performed": True,
        "package_name": state.get("instance_package_name"),
        "sam_package_id": state.get("instance_package_id"),
        "snapshot_digest": plan["snapshot_digest"],
        "sync_state": new_state,
        "delta": plan["counts"],
        "relationship_delta": plan["relationship_counts"],
        "relationship_creates": plan.get("relationship_creates") or [],
        "relationship_updates": plan.get("relationship_updates") or [],
        "relationship_deletes": plan.get("relationship_deletes") or [],
        "metadata_warnings": list(factory.warnings),
        "timings": {"total_seconds": round(perf_counter() - started, 3)},
    }
