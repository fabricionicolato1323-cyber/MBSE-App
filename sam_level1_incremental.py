"""Incremental SAM Level 1 synchronization for one managed model instance.

The reusable ArcadiaOA library is never rewritten after it is available. A verified
local manifest maps stable MBSE-App node and relationship identities to SAM IDs and
provides the baseline for an explicit, user-reviewed change set.

Supported in this stage:
* no-op detection without a SAM write;
* name-only UPDATEs of existing nodes;
* CREATE/DELETE of isolated nodes;
* CREATE/DELETE/UPDATE (replace) of OPERATIONAL_EXCHANGE relationships;
* FlowConnectionUsage ownership under an associated Communication Mean usage; and
* read-only migration of a legacy v1 manifest when the relationship delta can be
  proven to contain only additive OPERATIONAL_EXCHANGE relationships.

Other relationship types and Operational Scenario deltas remain deliberately
blocked. The writer never performs a partial structural synchronization or rebuilds
the complete instance silently.
"""

from __future__ import annotations

import copy
import hashlib
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

from exchange_transport import (
    ExchangeTransportError,
    relationship_identity,
    resolve_exchange_transport,
    transport_owner_record,
)
from sam_connection import SamSettings
from sam_level1_direct import _MetadataTolerantFactory
from sam_level1_managed_direct import _library_status
from sam_level1_sync import (
    SamLevel1SyncError,
    _create_characteristics,
    _documentation,
    _rows,
    _source_document,
    build_level1_sync_plan,
    level1_snapshot_digest,
)
from sam_level1_transactional import (
    ARCADIA_OA_LIBRARY_PACKAGE,
    _attribute_values,
    _children,
    _element_id,
    _element_name,
    _load_project,
    _resolve_project_value,
)
from sam_reload_safe_factory import ReloadSafeFactory

SYNC_STATE_KEY = "sam_sync"
LEGACY_SYNC_STATE_VERSION = 1
SYNC_STATE_VERSION = 2
TRANSPORT_OWNERSHIP_REVISION = 1
SUPPORTED_INCREMENTAL_RELATIONSHIP_TYPES = frozenset({"OPERATIONAL_EXCHANGE"})


def _digest(value: Any) -> str:
    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scenario_rows(
    model: dict[str, Any], scenarios: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    return [item for item in rows if item.get("valid") is not False]


def _graph(model: dict[str, Any]) -> dict[str, Any]:
    value = model.get("graph")
    return value if isinstance(value, dict) else {}


def sync_state_from_model(model: dict[str, Any]) -> dict[str, Any] | None:
    state = _graph(model).get(SYNC_STATE_KEY)
    if not isinstance(state, dict):
        return None
    try:
        version = int(state.get("version", 0))
    except (TypeError, ValueError):
        return None
    if version not in {LEGACY_SYNC_STATE_VERSION, SYNC_STATE_VERSION}:
        return None
    return copy.deepcopy(state)


def _nodes_by_id(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): copy.deepcopy(item)
        for item in _rows(model.get("nodes"))
        if item.get("id") is not None
    }


def _without_name(node: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(node)
    value.pop("name", None)
    return value


def _edge_identity(edge: dict[str, Any]) -> str:
    """Stable relationship identity; name/properties are intentionally excluded."""
    return relationship_identity(edge)


def _supported_edges_by_id(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for edge in _rows(model.get("edges")):
        if str(edge.get("type") or "") not in SUPPORTED_INCREMENTAL_RELATIONSHIP_TYPES:
            continue
        identity = _edge_identity(edge)
        if identity in result:
            raise SamLevel1SyncError(
                f"Relationship identity {identity!r} is duplicated in the local model."
            )
        result[identity] = copy.deepcopy(edge)
    return result


def _edge_fingerprint(model: dict[str, Any]) -> str:
    return _digest(
        sorted(
            _rows(model.get("edges")),
            key=lambda item: json.dumps(item, sort_keys=True, default=str),
        )
    )


def _legacy_other_edge_fingerprint(model: dict[str, Any]) -> str:
    rows = [
        copy.deepcopy(item)
        for item in _rows(model.get("edges"))
        if str(item.get("type") or "") not in SUPPORTED_INCREMENTAL_RELATIONSHIP_TYPES
    ]
    return _digest(sorted(rows, key=lambda item: json.dumps(item, sort_keys=True, default=str)))


def _other_edge_fingerprint(model: dict[str, Any]) -> str:
    rows: list[dict[str, Any]] = []
    for item in _rows(model.get("edges")):
        if str(item.get("type") or "") in SUPPORTED_INCREMENTAL_RELATIONSHIP_TYPES:
            continue
        normalized = copy.deepcopy(item)
        if str(normalized.get("type") or "") == "COMMUNICATION_MEAN":
            # exchange_refs expresses which flow usage is owned by this medium;
            # it is handled by the OPERATIONAL_EXCHANGE incremental change set.
            normalized.pop("exchange_refs", None)
        rows.append(normalized)
    return _digest(sorted(rows, key=lambda item: json.dumps(item, sort_keys=True, default=str)))


def _scenario_fingerprint(rows: list[dict[str, Any]]) -> str:
    return _digest(
        sorted(rows, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    )


def _descendants(project: Any, owner: Any) -> list[Any]:
    queue = list(_children(project, owner))
    result: list[Any] = []
    seen: set[str] = set()
    while queue:
        current = queue.pop(0)
        identity = _element_id(current) or f"object:{id(current)}"
        if identity in seen:
            continue
        seen.add(identity)
        result.append(current)
        queue.extend(_children(project, current))
    return result


def _unique_descendant_by_name(project: Any, package: Any, name: str) -> Any:
    matches = [
        item for item in _descendants(project, package) if _element_name(item) == name
    ]
    if len(matches) != 1:
        raise SamLevel1SyncError(
            f"Cannot adopt the existing SAM instance because source element {name!r} "
            f"matches {len(matches)} SAM descendants. Rename duplicate elements or create "
            "a fresh baseline before enabling incremental synchronization."
        )
    return matches[0]


def _relationship_name(edge: dict[str, Any]) -> str:
    return str(edge.get("name") or edge.get("type") or "Relationship").strip() or "Relationship"


def _transport_record(model: dict[str, Any], edge: dict[str, Any]) -> dict[str, Any]:
    try:
        return transport_owner_record(_rows(model.get("edges")), edge)
    except ExchangeTransportError as exc:
        raise SamLevel1SyncError(str(exc)) from exc


def _adopt_supported_relationship_elements(
    project: Any,
    package: Any,
    model: dict[str, Any],
    *,
    allow_missing: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    """Resolve supported relationship IDs by scoped, unique name.

    ``allow_missing`` is used only by the v1 additive migration path. Missing
    relationships are then candidates for CREATE; ambiguity always blocks.
    """
    descendants = _descendants(project, package)
    result: dict[str, Any] = {}
    missing: list[str] = []
    for relationship_id, edge in _supported_edges_by_id(model).items():
        name = _relationship_name(edge)
        matches = [item for item in descendants if _element_name(item) == name]
        if not matches and allow_missing:
            missing.append(relationship_id)
            continue
        if len(matches) != 1:
            raise SamLevel1SyncError(
                f"Cannot map Operational Exchange {name!r} to the managed SAM instance: "
                f"found {len(matches)} descendants with that name. No SAM write was performed."
            )
        result[relationship_id] = matches[0]
    return result, missing


def _relationship_records(
    model: dict[str, Any],
    relationship_elements: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for relationship_id, edge in _supported_edges_by_id(model).items():
        element = relationship_elements.get(relationship_id)
        if element is None:
            raise SamLevel1SyncError(
                f"No SAM relationship mapping is available for {relationship_id!r}."
            )
        sam_id = _element_id(element)
        if not sam_id:
            raise SamLevel1SyncError(
                f"SAM relationship {_relationship_name(edge)!r} has no stable ID."
            )
        owner = _transport_record(model, edge)
        records[relationship_id] = {
            "sam_id": sam_id,
            "type": str(edge.get("type") or ""),
            "source_id": str(edge.get("source") or ""),
            "target_id": str(edge.get("target") or ""),
            "key": edge.get("key", 0),
            "name": _relationship_name(edge),
            "source": copy.deepcopy(edge),
            **owner,
        }
    return records


def _build_state(
    model: dict[str, Any],
    scenarios: list[dict[str, Any]],
    *,
    settings: SamSettings,
    package_name: str,
    package_id: str | None,
    node_elements: dict[str, Any],
    relationship_elements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = _nodes_by_id(model)
    supported_relationships = _supported_edges_by_id(model)
    if relationship_elements is None:
        if supported_relationships:
            raise SamLevel1SyncError(
                "Incremental baseline adoption did not resolve Operational Exchange IDs."
            )
        relationship_elements = {}
    return {
        "version": SYNC_STATE_VERSION,
        "transport_ownership_revision": TRANSPORT_OWNERSHIP_REVISION,
        "project_id": settings.project_id,
        "library_package_name": ARCADIA_OA_LIBRARY_PACKAGE,
        "instance_package_name": package_name,
        "instance_package_id": package_id,
        "snapshot_digest": level1_snapshot_digest(model, scenarios),
        "nodes": {
            node_id: {
                "sam_id": _element_id(node_elements[node_id]),
                "type": str(node.get("type") or ""),
                "name": str(node.get("name") or ""),
                "source": node,
            }
            for node_id, node in nodes.items()
        },
        "relationships": _relationship_records(model, relationship_elements),
        "relationship_tracking_complete": True,
        "other_edges_fingerprint": _other_edge_fingerprint(model),
        "edges_fingerprint": _edge_fingerprint(model),
        "scenarios_fingerprint": _scenario_fingerprint(scenarios),
    }


def _managed_instance(project: Any, state: dict[str, Any]) -> Any:
    package_id = str(state.get("instance_package_id") or "")
    package = project.find_element_by_id(package_id) if package_id else None
    if package is not None:
        return package
    name = str(state.get("instance_package_name") or "")
    matches = list(project.find_elements_by_name(name) or []) if name else []
    if len(matches) != 1:
        raise SamLevel1SyncError(
            "The managed SAM Level 1 instance recorded by MBSE-App can no longer be resolved. "
            "No incremental write was performed."
        )
    return matches[0]


def migrate_legacy_relationship_state(
    model: dict[str, Any],
    *,
    scenarios: list[dict[str, Any]],
    state: dict[str, Any],
    settings: SamSettings,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Read-only v1->v2 migration for provably additive Operational Exchanges.

    The v1 manifest stored only a global edge fingerprint. We therefore migrate a
    changed v1 baseline only when every relationship absent from SAM is a current
    OPERATIONAL_EXCHANGE and removing exactly those relationships reproduces the
    recorded v1 fingerprint. This proves the old topology without guessing.
    """
    try:
        version = int(state.get("version", 0))
    except (TypeError, ValueError):
        version = 0
    if version == SYNC_STATE_VERSION:
        return copy.deepcopy(state)
    if version != LEGACY_SYNC_STATE_VERSION:
        raise SamLevel1SyncError("Unsupported SAM synchronization manifest version.")
    if state.get("project_id") != settings.project_id:
        raise SamLevel1SyncError("The legacy SAM manifest belongs to a different project.")
    if _scenario_fingerprint(scenarios) != state.get("scenarios_fingerprint"):
        raise SamLevel1SyncError(
            "Operational Scenarios changed while migrating the legacy SAM baseline. "
            "Scenario incremental sync is still pending; no SAM write was performed."
        )

    _, _, project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    package = _managed_instance(project, state)
    mapped, missing_ids = _adopt_supported_relationship_elements(
        project, package, model, allow_missing=True
    )

    candidate_previous = copy.deepcopy(model)
    missing_set = set(missing_ids)
    candidate_previous["edges"] = [
        copy.deepcopy(edge)
        for edge in _rows(model.get("edges"))
        if _edge_identity(edge) not in missing_set
    ]
    if _edge_fingerprint(candidate_previous) != state.get("edges_fingerprint"):
        raise SamLevel1SyncError(
            "The legacy SAM relationship baseline cannot be migrated safely from this "
            "change set. Only provably additive OPERATIONAL_EXCHANGE changes are accepted "
            "for the first v1-to-v2 migration. No SAM data was changed."
        )

    records = _relationship_records(candidate_previous, mapped)
    # A v1 manifest was written by the pre-transport-ownership writer: every
    # Operational Exchange was under oa_operationalBehavior, regardless of refs.
    for record in records.values():
        record["owner_kind"] = "behavior"
        record["owner_relationship_id"] = None
        record["owner_name"] = "oa_operationalBehavior"

    migrated = copy.deepcopy(state)
    migrated["version"] = SYNC_STATE_VERSION
    migrated["relationships"] = records
    migrated["relationship_tracking_complete"] = True
    migrated["other_edges_fingerprint"] = _legacy_other_edge_fingerprint(candidate_previous)
    return migrated


def adopt_existing_instance(
    model: dict[str, Any],
    *,
    scenarios: list[dict[str, Any]],
    settings: SamSettings,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any] | None:
    """Adopt an already verified Level 1 instance as the incremental baseline."""
    plan = build_level1_sync_plan(
        model, scenarios=scenarios, project_id=settings.project_id
    )
    _, _, project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    matches = list(project.find_elements_by_name(str(plan["package_name"])) or [])
    if not matches:
        prefix = "MBSE_Instance_"
        candidates = [
            item
            for item in getattr(project, "environment", []) or []
            if _element_name(item).startswith(prefix)
            and str(plan["model_name"]).replace(" ", "_").lower()
            in _element_name(item).lower()
        ]
        if len(candidates) == 1:
            matches = candidates
    if len(matches) != 1:
        return None

    package = matches[0]
    node_elements: dict[str, Any] = {}
    for node_id, node in _nodes_by_id(model).items():
        node_elements[node_id] = _unique_descendant_by_name(
            project,
            package,
            str(node.get("name") or node_id),
        )
    relationship_elements, missing = _adopt_supported_relationship_elements(
        project, package, model
    )
    if missing:
        return None
    return _build_state(
        model,
        scenarios,
        settings=settings,
        package_name=_element_name(package),
        package_id=_element_id(package),
        node_elements=node_elements,
        relationship_elements=relationship_elements,
    )


def _relationship_change_set(
    model: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    current = _supported_edges_by_id(model)
    previous = state.get("relationships") if isinstance(state.get("relationships"), dict) else {}
    current_ids = set(current)
    previous_ids = set(previous)
    creates = [
        {"relationship_id": identity, "edge": copy.deepcopy(current[identity])}
        for identity in sorted(current_ids - previous_ids)
    ]
    deletes: list[dict[str, Any]] = []
    for identity in sorted(previous_ids - current_ids):
        record = previous.get(identity) if isinstance(previous.get(identity), dict) else {}
        deletes.append(
            {
                "relationship_id": identity,
                "sam_id": record.get("sam_id"),
                "old_name": str(record.get("name") or ""),
                "type": str(record.get("type") or ""),
                "edge": copy.deepcopy(record.get("source") or {}),
                "old_owner_kind": str(record.get("owner_kind") or "behavior"),
                "old_owner_name": str(record.get("owner_name") or "oa_operationalBehavior"),
            }
        )
    updates: list[dict[str, Any]] = []
    unchanged = 0
    for identity in sorted(current_ids & previous_ids):
        record = previous.get(identity) if isinstance(previous.get(identity), dict) else {}
        old_edge = record.get("source") if isinstance(record.get("source"), dict) else {}
        new_edge = current[identity]
        new_owner = _transport_record(model, new_edge)
        old_owner_kind = str(record.get("owner_kind") or "behavior")
        old_owner_relationship_id = record.get("owner_relationship_id")
        owner_changed = (
            old_owner_kind != str(new_owner.get("owner_kind") or "behavior")
            or old_owner_relationship_id != new_owner.get("owner_relationship_id")
        )
        if old_edge == new_edge and not owner_changed:
            unchanged += 1
            continue
        updates.append(
            {
                "relationship_id": identity,
                "sam_id": record.get("sam_id"),
                "old_name": str(record.get("name") or _relationship_name(old_edge)),
                "new_name": _relationship_name(new_edge),
                "old_edge": copy.deepcopy(old_edge),
                "edge": copy.deepcopy(new_edge),
                "old_owner_kind": old_owner_kind,
                "old_owner_name": str(record.get("owner_name") or "oa_operationalBehavior"),
                "new_owner_kind": str(new_owner.get("owner_kind") or "behavior"),
                "new_owner_name": str(new_owner.get("owner_name") or "oa_operationalBehavior"),
                "new_owner_relationship_id": new_owner.get("owner_relationship_id"),
                "owner_changed": owner_changed,
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


def build_incremental_plan(
    model: dict[str, Any],
    *,
    scenarios: list[dict[str, Any]],
    settings: SamSettings,
) -> dict[str, Any]:
    """Return a read-only node + supported-relationship change set."""
    state = sync_state_from_model(model)
    current_digest = level1_snapshot_digest(model, scenarios)
    current_nodes = _nodes_by_id(model)
    if state is None or state.get("project_id") != settings.project_id:
        return {
            "mode": "baseline_required",
            "supported": True,
            "snapshot_digest": current_digest,
            "counts": {
                "create": len(current_nodes),
                "update": 0,
                "delete": 0,
                "unchanged": 0,
            },
            "creates": [
                {"source_id": node_id, "node": node}
                for node_id, node in sorted(current_nodes.items())
            ],
            "updates": [],
            "deletes": [],
            "relationship_counts": {
                "create": len(_rows(model.get("edges"))),
                "update": 0,
                "delete": 0,
                "unchanged": 0,
            },
            "relationship_creates": [],
            "relationship_updates": [],
            "relationship_deletes": [],
            "reason": "No incremental baseline is recorded for this SAM project yet.",
        }
    ownership_current = (
        int(state.get("transport_ownership_revision", 0) or 0)
        == TRANSPORT_OWNERSHIP_REVISION
    )
    if current_digest == state.get("snapshot_digest") and ownership_current:
        return {
            "mode": "incremental_noop",
            "supported": True,
            "snapshot_digest": current_digest,
            "counts": {
                "create": 0,
                "update": 0,
                "delete": 0,
                "unchanged": len(current_nodes),
            },
            "creates": [],
            "updates": [],
            "deletes": [],
            "relationship_counts": {
                "create": 0,
                "update": 0,
                "delete": 0,
                "unchanged": len(_rows(model.get("edges"))),
            },
            "relationship_creates": [],
            "relationship_updates": [],
            "relationship_deletes": [],
            "unsupported_changes": [],
            "relationship_changes_pending": False,
            "scenario_changes_pending": False,
            "instance_package_name": state.get("instance_package_name"),
        }

    previous_nodes = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}
    current_ids = set(current_nodes)
    previous_ids = set(previous_nodes)
    added_ids = sorted(current_ids - previous_ids)
    removed_ids = sorted(previous_ids - current_ids)

    creates = [
        {"source_id": node_id, "node": copy.deepcopy(current_nodes[node_id])}
        for node_id in added_ids
    ]
    deletes = []
    for node_id in removed_ids:
        record = previous_nodes.get(node_id)
        if not isinstance(record, dict):
            record = {}
        deletes.append(
            {
                "source_id": node_id,
                "sam_id": record.get("sam_id"),
                "old_name": str(record.get("name") or ""),
                "type": str(record.get("type") or ""),
                "source": copy.deepcopy(record.get("source") or {}),
            }
        )

    unsupported: list[str] = []
    try:
        state_version = int(state.get("version", 0))
    except (TypeError, ValueError):
        state_version = 0

    scenarios_changed = (
        _scenario_fingerprint(scenarios) != state.get("scenarios_fingerprint")
    )
    if scenarios_changed:
        unsupported.append(
            "operational scenarios changed; scenario incremental sync is pending"
        )

    if state_version == LEGACY_SYNC_STATE_VERSION:
        relationship_changed = _edge_fingerprint(model) != state.get("edges_fingerprint")
        if relationship_changed:
            unsupported.append(
                "legacy relationship baseline requires read-only v1-to-v2 migration before synchronization"
            )
        relationship_delta = {
            "create": [], "update": [], "delete": [], "unchanged": 0,
            "counts": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
        }
        relationship_changes_pending = relationship_changed
    else:
        relationship_delta = _relationship_change_set(model, state)
        if ownership_current:
            other_relationship_changed = (
                _other_edge_fingerprint(model) != state.get("other_edges_fingerprint")
            )
        else:
            # Existing v2 manifests were written before exchange_refs became an
            # ownership signal; compare using the legacy fingerprint once.
            other_relationship_changed = (
                _legacy_other_edge_fingerprint(model) != state.get("other_edges_fingerprint")
            )
        if other_relationship_changed:
            unsupported.append(
                "relationship types outside OPERATIONAL_EXCHANGE changed; their incremental handlers are pending"
            )
        relationship_changes_pending = other_relationship_changed

    updates: list[dict[str, Any]] = []
    for node_id in sorted(current_ids & previous_ids):
        current = current_nodes[node_id]
        previous_record = (
            previous_nodes.get(node_id)
            if isinstance(previous_nodes.get(node_id), dict)
            else {}
        )
        previous = (
            previous_record.get("source")
            if isinstance(previous_record.get("source"), dict)
            else {}
        )
        if current == previous:
            continue
        if str(current.get("type") or "") != str(previous_record.get("type") or ""):
            unsupported.append(f"element type changed for {node_id}")
            continue
        if _without_name(current) != _without_name(previous):
            unsupported.append(f"non-name properties changed for {node_id}")
            continue
        updates.append(
            {
                "source_id": node_id,
                "sam_id": previous_record.get("sam_id"),
                "old_name": str(previous.get("name") or ""),
                "new_name": str(current.get("name") or ""),
            }
        )

    for item in relationship_delta["create"] + relationship_delta["update"]:
        edge = item.get("edge") if isinstance(item.get("edge"), dict) else {}
        source_id = str(edge.get("source") or "")
        target_id = str(edge.get("target") or "")
        if source_id not in current_nodes or target_id not in current_nodes:
            unsupported.append(
                f"Operational Exchange {_relationship_name(edge)!r} has an unresolved endpoint"
            )
        try:
            resolve_exchange_transport(_rows(model.get("edges")), edge)
        except ExchangeTransportError as exc:
            unsupported.append(str(exc))

    removed_set = set(removed_ids)
    for edge in _supported_edges_by_id(model).values():
        if str(edge.get("source") or "") in removed_set or str(edge.get("target") or "") in removed_set:
            unsupported.append(
                f"node deletion would leave Operational Exchange {_relationship_name(edge)!r} dangling"
            )

    unchanged = max(0, len(current_ids & previous_ids) - len(updates))
    relationship_counts = relationship_delta["counts"]
    has_relationship_delta = any(
        int(relationship_counts.get(key, 0)) > 0 for key in ("create", "update", "delete")
    )
    mode = (
        "incremental_noop"
        if not creates and not updates and not deletes and not has_relationship_delta and not unsupported
        else "incremental_change_set"
    )
    return {
        "mode": mode,
        "supported": not unsupported,
        "snapshot_digest": current_digest,
        "counts": {
            "create": len(creates),
            "update": len(updates),
            "delete": len(deletes),
            "unchanged": unchanged,
        },
        "creates": creates,
        "updates": updates,
        "deletes": deletes,
        "relationship_counts": relationship_counts,
        "relationship_creates": relationship_delta["create"],
        "relationship_updates": relationship_delta["update"],
        "relationship_deletes": relationship_delta["delete"],
        "relationship_changes_pending": relationship_changes_pending,
        "scenario_changes_pending": scenarios_changed,
        "unsupported_changes": unsupported,
        "instance_package_name": state.get("instance_package_name"),
    }


def _incremental_create_owner(
    project: Any,
    package: Any,
    node_type: str,
) -> Any:
    if node_type in {"OperationalEntity", "OperationalActor"}:
        return _unique_descendant_by_name(project, package, "oa_operationalContext")
    if node_type == "OperationalActivity":
        return _unique_descendant_by_name(project, package, "oa_operationalBehavior")
    if node_type == "OperationalCapability":
        return package
    raise SamLevel1SyncError(
        f"Incremental CREATE does not support node type {node_type!r}."
    )


def _stage_incremental_creates(
    connector: Any,
    project: Any,
    resolved_factory: type[Any],
    state: dict[str, Any],
    creates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    if not creates:
        return [], []

    package = _managed_instance(project, state)
    library = _library_status(project)
    if not library.get("loaded"):
        raise SamLevel1SyncError(
            "The reusable ArcadiaOA library is not complete. Incremental CREATE was not started."
        )
    definitions = library["definitions"]
    raw_factory = resolved_factory(project, connector)
    factory = _MetadataTolerantFactory(ReloadSafeFactory(project, raw_factory))
    staged: list[dict[str, Any]] = []

    for item in creates:
        node = item.get("node") if isinstance(item.get("node"), dict) else {}
        source_id = str(item.get("source_id") or "")
        node_type = str(node.get("type") or "")
        final_name = str(node.get("name") or source_id)
        owner = _incremental_create_owner(project, package, node_type)
        staging_name = f"__MBSE_NEW_{uuid4().hex[:10]}"

        try:
            if node_type == "OperationalEntity":
                element = factory.create_part_usage(
                    name=staging_name,
                    owner=owner,
                    part_definition=[definitions["OperationalEntity"]],
                )
            elif node_type == "OperationalActor":
                element = factory.create_part_usage(
                    name=staging_name,
                    owner=owner,
                    part_definition=[definitions["OperationalActor"]],
                    is_actor=True,
                )
            elif node_type == "OperationalActivity":
                element = factory.create_action_usage(
                    name=staging_name,
                    owner=owner,
                    action_definition=[definitions["OperationalActivity"]],
                )
            elif node_type == "OperationalCapability":
                element = factory.create_requirement_usage(
                    name=staging_name,
                    owner=owner,
                    requirement_definition=definitions["OperationalCapability"],
                    req_id=source_id,
                )
            else:
                raise SamLevel1SyncError(
                    f"Incremental CREATE does not support node type {node_type!r}."
                )
            _documentation(factory, element, _source_document(node, "element"))
            _create_characteristics(factory, element, node)
        except Exception as exc:
            raise SamLevel1SyncError(
                "SAM incremental CREATE failed while staging "
                f"{final_name!r}: {exc}. A temporary __MBSE_NEW_* element may remain; "
                "the final model element was not published."
            ) from exc

        staged.append(
            {
                "source_id": source_id,
                "sam_id": _element_id(element),
                "staging_name": staging_name,
                "final_name": final_name,
                "node": copy.deepcopy(node),
            }
        )
    return staged, list(factory.warnings)


def _node_sam_ids(
    state: dict[str, Any], staged_nodes: list[dict[str, Any]]
) -> dict[str, str]:
    result: dict[str, str] = {}
    previous = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}
    for node_id, record in previous.items():
        if isinstance(record, dict) and record.get("sam_id"):
            result[str(node_id)] = str(record["sam_id"])
    for item in staged_nodes:
        if item.get("source_id") and item.get("sam_id"):
            result[str(item["source_id"])] = str(item["sam_id"])
    return result


def _stage_incremental_relationships(
    connector: Any,
    project: Any,
    resolved_factory: type[Any],
    state: dict[str, Any],
    *,
    model: dict[str, Any],
    node_sam_ids: dict[str, str],
    creates: list[dict[str, Any]],
    updates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    work: list[tuple[str, dict[str, Any]]] = [
        ("create", item) for item in creates
    ] + [("update", item) for item in updates]
    if not work:
        return [], []

    package = _managed_instance(project, state)
    behavior = _unique_descendant_by_name(project, package, "oa_operationalBehavior")
    library = _library_status(project)
    if not library.get("loaded"):
        raise SamLevel1SyncError(
            "The reusable ArcadiaOA library is not complete. Relationship CREATE was not started."
        )
    definitions = library["definitions"]
    raw_factory = resolved_factory(project, connector)
    factory = _MetadataTolerantFactory(ReloadSafeFactory(project, raw_factory))
    staged: list[dict[str, Any]] = []

    for operation, item in work:
        edge = item.get("edge") if isinstance(item.get("edge"), dict) else {}
        if str(edge.get("type") or "") != "OPERATIONAL_EXCHANGE":
            raise SamLevel1SyncError(
                f"Incremental relationship writer does not support {edge.get('type')!r}."
            )
        source_id = str(edge.get("source") or "")
        target_id = str(edge.get("target") or "")
        source_sam_id = node_sam_ids.get(source_id)
        target_sam_id = node_sam_ids.get(target_id)
        source = project.find_element_by_id(source_sam_id) if source_sam_id else None
        target = project.find_element_by_id(target_sam_id) if target_sam_id else None
        if source is None or target is None:
            raise SamLevel1SyncError(
                f"Operational Exchange {_relationship_name(edge)!r} endpoints could not be resolved in SAM."
            )
        behavior = project.find_element_by_id(_element_id(behavior)) or behavior
        try:
            transport = resolve_exchange_transport(_rows(model.get("edges")), edge)
        except ExchangeTransportError as exc:
            raise SamLevel1SyncError(str(exc)) from exc
        owner = behavior
        owner_kind = "behavior"
        owner_name = "oa_operationalBehavior"
        owner_relationship_id = None
        if transport is not None:
            owner = _unique_descendant_by_name(
                project, package, str(transport.get("name") or "Communication Mean")
            )
            owner_kind = "communication_mean"
            owner_name = str(transport.get("name") or "Communication Mean")
            owner_relationship_id = relationship_identity(transport)
        owner = project.find_element_by_id(_element_id(owner)) or owner
        definition = project.find_element_by_id(_element_id(definitions["OperationalExchange"])) or definitions["OperationalExchange"]
        staging_name = f"__MBSE_REL_NEW_{uuid4().hex[:10]}"
        try:
            relationship = factory.create_flow_connection_usage(
                name=staging_name,
                owner=owner,
                flow_connection_definition=[definition],
                source=[source],
                target=[target],
                source_feature=source,
                target_feature=[target],
                related_feature=[source, target],
                is_directed=True,
            )
            _documentation(factory, relationship, _source_document(edge, "relationship"))
        except Exception as exc:
            raise SamLevel1SyncError(
                "SAM incremental Operational Exchange CREATE failed while staging "
                f"{_relationship_name(edge)!r}: {exc}. A temporary __MBSE_REL_NEW_* "
                "element may remain; the reviewed relationship was not published."
            ) from exc
        staged.append(
            {
                "operation": operation,
                "relationship_id": item.get("relationship_id"),
                "old_sam_id": item.get("sam_id") if operation == "update" else None,
                "sam_id": _element_id(relationship),
                "staging_name": staging_name,
                "final_name": _relationship_name(edge),
                "source_id": source_id,
                "target_id": target_id,
                "source_sam_id": source_sam_id,
                "target_sam_id": target_sam_id,
                "owner_sam_id": _element_id(owner),
                "owner_kind": owner_kind,
                "owner_name": owner_name,
                "owner_relationship_id": owner_relationship_id,
                "edge": copy.deepcopy(edge),
            }
        )
    return staged, list(factory.warnings)


def _delete_owned_tree(element: Any, project: Any) -> None:
    descendants = _descendants(project, element)
    for child in reversed(descendants):
        delete = getattr(child, "delete", None)
        if callable(delete):
            delete()
    delete = getattr(element, "delete", None)
    if not callable(delete):
        raise SamLevel1SyncError(
            f"SAM element {_element_id(element)!r} does not expose the PySAM delete operation."
        )
    delete()


def _relationship_endpoint_ids(project: Any, relationship: Any) -> set[str]:
    """Best-effort fresh endpoint proof across PySAM JSON/scripting shapes."""
    attrs = (
        "source", "_source", "target", "_target",
        "source_feature", "_source_feature", "sourceFeature", "_sourceFeature",
        "target_feature", "_target_feature", "targetFeature", "_targetFeature",
        "related_feature", "_related_feature", "relatedFeature", "_relatedFeature",
        "referenced_feature", "_referenced_feature", "referencedFeature", "_referencedFeature",
    )
    values: list[Any] = []
    for item in [relationship] + _descendants(project, relationship):
        values.extend(_attribute_values(item, attrs))
    result: set[str] = set()
    for value in values:
        resolved = _resolve_project_value(project, value)
        identity = _element_id(resolved)
        if identity:
            result.add(identity)
        elif isinstance(value, str) and value.strip():
            result.add(value.strip())
    return result


def _relationship_owner_id(project: Any, relationship: Any) -> str | None:
    for attr in ("owner", "_owner"):
        try:
            value = getattr(relationship, attr, None)
        except Exception:
            value = None
        if value is None:
            continue
        resolved = _resolve_project_value(project, value)
        identity = _element_id(resolved)
        if identity:
            return identity
    return None


def sync_level1_incremental(
    model: dict[str, Any],
    *,
    scenarios: list[dict[str, Any]],
    settings: SamSettings,
    expected_digest: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Adopt a baseline, skip no-ops, or apply one reviewed Level 1 change set."""
    total_started = perf_counter()
    state = sync_state_from_model(model)
    if state is None or state.get("project_id") != settings.project_id:
        adopt_started = perf_counter()
        adopted = adopt_existing_instance(
            model,
            scenarios=scenarios,
            settings=settings,
            connector_class=connector_class,
            project_manager_class=project_manager_class,
            factory_class=factory_class,
        )
        if adopted is not None:
            return {
                "status": "already_synced",
                "mode": "incremental_baseline_adopted",
                "sam_write_performed": False,
                "package_name": adopted["instance_package_name"],
                "sam_package_id": adopted.get("instance_package_id"),
                "snapshot_digest": adopted["snapshot_digest"],
                "sync_state": adopted,
                "delta": {
                    "create": 0,
                    "update": 0,
                    "delete": 0,
                    "unchanged": len(adopted["nodes"]),
                },
                "relationship_delta": {
                    "create": 0,
                    "update": 0,
                    "delete": 0,
                    "unchanged": len(adopted.get("relationships") or {}),
                },
                "timings": {
                    "adoption_seconds": round(perf_counter() - adopt_started, 3),
                    "total_seconds": round(perf_counter() - total_started, 3),
                },
            }
        return {"status": "baseline_required", "sync_state": None}

    plan = build_incremental_plan(model, scenarios=scenarios, settings=settings)
    if expected_digest and expected_digest != plan["snapshot_digest"]:
        raise SamLevel1SyncError(
            "The model changed after the incremental change set was reviewed. "
            "Review it again before synchronizing."
        )
    if plan["mode"] == "incremental_noop":
        return {
            "status": "already_synced",
            "mode": "incremental_noop",
            "sam_write_performed": False,
            "package_name": state.get("instance_package_name"),
            "sam_package_id": state.get("instance_package_id"),
            "snapshot_digest": plan["snapshot_digest"],
            "sync_state": state,
            "delta": plan["counts"],
            "relationship_delta": plan.get("relationship_counts") or {},
            "timings": {"total_seconds": round(perf_counter() - total_started, 3)},
        }
    if not plan["supported"]:
        raise SamLevel1SyncError(
            "This reviewed Level 1 change set contains changes whose incremental handler "
            "is not enabled yet. No SAM data was changed. Pending delta: "
            + "; ".join(plan.get("unsupported_changes") or [])
        )

    connect_started = perf_counter()
    connector, _, project, resolved_factory = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    connection_seconds = perf_counter() - connect_started

    updates = list(plan.get("updates") or [])
    creates = list(plan.get("creates") or [])
    deletes = list(plan.get("deletes") or [])
    relationship_creates = list(plan.get("relationship_creates") or [])
    relationship_updates = list(plan.get("relationship_updates") or [])
    relationship_deletes = list(plan.get("relationship_deletes") or [])

    for item in updates + deletes:
        sam_id = str(item.get("sam_id") or "")
        element = project.find_element_by_id(sam_id) if sam_id else None
        if element is None:
            raise SamLevel1SyncError(
                f"The SAM element mapped to MBSE-App id {item.get('source_id')!r} no longer exists. "
                "No incremental write was performed."
            )
    for item in relationship_updates + relationship_deletes:
        sam_id = str(item.get("sam_id") or "")
        element = project.find_element_by_id(sam_id) if sam_id else None
        if element is None:
            raise SamLevel1SyncError(
                f"The SAM relationship mapped to {item.get('relationship_id')!r} no longer exists. "
                "No incremental write was performed."
            )

    current_nodes = _nodes_by_id(model)
    create_node_ids = {str(item.get("source_id") or "") for item in creates}
    previous_nodes = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}
    for item in relationship_creates + relationship_updates:
        edge = item.get("edge") if isinstance(item.get("edge"), dict) else {}
        for endpoint in (str(edge.get("source") or ""), str(edge.get("target") or "")):
            record = previous_nodes.get(endpoint) if isinstance(previous_nodes.get(endpoint), dict) else {}
            if endpoint not in create_node_ids and not record.get("sam_id"):
                raise SamLevel1SyncError(
                    f"Relationship endpoint {endpoint!r} has no verified SAM mapping. No write was performed."
                )
            if endpoint not in current_nodes:
                raise SamLevel1SyncError(
                    f"Relationship endpoint {endpoint!r} is absent from the reviewed snapshot. No write was performed."
                )

    write_started = perf_counter()
    staged_nodes, node_metadata_warnings = _stage_incremental_creates(
        connector,
        project,
        resolved_factory,
        state,
        creates,
    )
    node_ids = _node_sam_ids(state, staged_nodes)
    staged_relationships, relationship_metadata_warnings = _stage_incremental_relationships(
        connector,
        project,
        resolved_factory,
        state,
        model=model,
        node_sam_ids=node_ids,
        creates=relationship_creates,
        updates=relationship_updates,
    )

    has_write = bool(
        updates or deletes or staged_nodes or relationship_deletes or staged_relationships
    )
    if has_write:
        try:
            project.start_transactional_mode()

            relationship_old_items = relationship_deletes + relationship_updates
            for item in relationship_old_items:
                element = project.find_element_by_id(str(item.get("sam_id") or ""))
                if element is None:
                    raise SamLevel1SyncError(
                        f"SAM relationship delete target {item.get('relationship_id')!r} disappeared before commit."
                    )
                _delete_owned_tree(element, project)

            for item in updates:
                element = project.find_element_by_id(str(item.get("sam_id") or ""))
                if element is None:
                    raise SamLevel1SyncError(
                        f"SAM update target {item.get('source_id')!r} disappeared before commit."
                    )
                element.name = item["new_name"]
            for item in staged_nodes:
                element = project.find_element_by_id(str(item.get("sam_id") or ""))
                if element is None:
                    raise SamLevel1SyncError(
                        f"Staged SAM element {item.get('source_id')!r} disappeared before publication."
                    )
                element.name = item["final_name"]
            for item in staged_relationships:
                element = project.find_element_by_id(str(item.get("sam_id") or ""))
                if element is None:
                    raise SamLevel1SyncError(
                        f"Staged SAM relationship {item.get('relationship_id')!r} disappeared before publication."
                    )
                element.name = item["final_name"]
            for item in deletes:
                element = project.find_element_by_id(str(item.get("sam_id") or ""))
                if element is None:
                    raise SamLevel1SyncError(
                        f"SAM delete target {item.get('source_id')!r} disappeared before commit."
                    )
                _delete_owned_tree(element, project)
            project.stop_transactional_mode()
        except Exception as exc:
            if isinstance(exc, SamLevel1SyncError):
                raise
            raise SamLevel1SyncError(
                f"SAM incremental change-set transaction failed: {exc}"
            ) from exc
    write_seconds = perf_counter() - write_started

    verify_started = perf_counter()
    _, _, verified_project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=resolved_factory,
    )
    for item in updates:
        current = verified_project.find_element_by_id(str(item.get("sam_id") or ""))
        if current is None or _element_name(current) != item["new_name"]:
            raise SamLevel1SyncError(
                f"SAM accepted the change set, but UPDATE verification failed for {item.get('source_id')!r}."
            )
    for item in staged_nodes:
        current = verified_project.find_element_by_id(str(item.get("sam_id") or ""))
        if current is None or _element_name(current) != item["final_name"]:
            raise SamLevel1SyncError(
                f"SAM accepted the change set, but CREATE verification failed for {item.get('source_id')!r}."
            )
    for item in deletes:
        current = verified_project.find_element_by_id(str(item.get("sam_id") or ""))
        if current is not None:
            raise SamLevel1SyncError(
                f"SAM accepted the change set, but DELETE verification failed for {item.get('source_id')!r}."
            )

    for item in relationship_deletes + relationship_updates:
        old = verified_project.find_element_by_id(str(item.get("sam_id") or ""))
        if old is not None:
            raise SamLevel1SyncError(
                f"SAM accepted the change set, but old relationship removal verification failed for {item.get('relationship_id')!r}."
            )

    endpoint_verification_warnings: list[str] = []
    for item in staged_relationships:
        current = verified_project.find_element_by_id(str(item.get("sam_id") or ""))
        if current is None or _element_name(current) != item["final_name"]:
            raise SamLevel1SyncError(
                f"SAM accepted the change set, but Operational Exchange verification failed for {item.get('relationship_id')!r}."
            )
        endpoint_ids = _relationship_endpoint_ids(verified_project, current)
        expected = {str(item["source_sam_id"]), str(item["target_sam_id"])}
        if endpoint_ids:
            if not expected.issubset(endpoint_ids):
                raise SamLevel1SyncError(
                    f"SAM reloaded Operational Exchange {item['final_name']!r}, but its endpoints do not match the reviewed source/target."
                )
        else:
            endpoint_verification_warnings.append(
                f"Fresh SAM reload verified Operational Exchange {item['final_name']!r} by stable ID/name; "
                "PySAM did not expose connector endpoint references for an additional endpoint proof."
            )
        owner_id = _relationship_owner_id(verified_project, current)
        expected_owner_id = str(item.get("owner_sam_id") or "")
        if owner_id and expected_owner_id and owner_id != expected_owner_id:
            raise SamLevel1SyncError(
                f"SAM reloaded Operational Exchange {item['final_name']!r}, but its owner does not match "
                f"the reviewed transport {item.get('owner_name')!r}."
            )
        if not owner_id:
            endpoint_verification_warnings.append(
                f"Fresh SAM reload verified Operational Exchange {item['final_name']!r}; PySAM did not expose "
                "its owner for an additional transport-ownership proof."
            )
    verification_seconds = perf_counter() - verify_started

    new_state = copy.deepcopy(state)
    new_state["version"] = SYNC_STATE_VERSION
    new_state["transport_ownership_revision"] = TRANSPORT_OWNERSHIP_REVISION
    current_nodes = _nodes_by_id(model)
    new_state.setdefault("nodes", {})
    for item in updates:
        node_id = str(item["source_id"])
        new_state["nodes"][node_id]["name"] = item["new_name"]
        new_state["nodes"][node_id]["source"] = current_nodes[node_id]
    for item in staged_nodes:
        node_id = str(item["source_id"])
        node = current_nodes[node_id]
        new_state["nodes"][node_id] = {
            "sam_id": item["sam_id"],
            "type": str(node.get("type") or ""),
            "name": str(node.get("name") or ""),
            "source": copy.deepcopy(node),
        }
    for item in deletes:
        new_state["nodes"].pop(str(item["source_id"]), None)

    relationships = new_state.get("relationships") if isinstance(new_state.get("relationships"), dict) else {}
    relationships = copy.deepcopy(relationships)
    for item in relationship_deletes:
        relationships.pop(str(item.get("relationship_id") or ""), None)
    for item in relationship_updates:
        relationships.pop(str(item.get("relationship_id") or ""), None)
    for item in staged_relationships:
        relationship_id = str(item.get("relationship_id") or "")
        edge = item["edge"]
        relationships[relationship_id] = {
            "sam_id": item["sam_id"],
            "type": str(edge.get("type") or ""),
            "source_id": str(edge.get("source") or ""),
            "target_id": str(edge.get("target") or ""),
            "key": edge.get("key", 0),
            "name": _relationship_name(edge),
            "source": copy.deepcopy(edge),
            "owner_kind": item.get("owner_kind"),
            "owner_relationship_id": item.get("owner_relationship_id"),
            "owner_name": item.get("owner_name"),
        }
    new_state["relationships"] = relationships
    new_state["relationship_tracking_complete"] = True
    new_state["snapshot_digest"] = plan["snapshot_digest"]
    new_state["other_edges_fingerprint"] = _other_edge_fingerprint(model)
    new_state["edges_fingerprint"] = _edge_fingerprint(model)
    new_state["scenarios_fingerprint"] = _scenario_fingerprint(scenarios)

    metadata_warnings = (
        node_metadata_warnings + relationship_metadata_warnings + endpoint_verification_warnings
    )
    return {
        "status": "synced",
        "mode": "incremental_change_set",
        "sam_write_performed": has_write,
        "package_name": state.get("instance_package_name"),
        "sam_package_id": state.get("instance_package_id"),
        "snapshot_digest": plan["snapshot_digest"],
        "sync_state": new_state,
        "delta": plan["counts"],
        "relationship_delta": plan.get("relationship_counts") or {},
        "relationship_creates": plan.get("relationship_creates") or [],
        "relationship_updates": plan.get("relationship_updates") or [],
        "relationship_deletes": plan.get("relationship_deletes") or [],
        "metadata_warnings": metadata_warnings,
        "timings": {
            "connection_seconds": round(connection_seconds, 3),
            "write_seconds": round(write_seconds, 3),
            "verification_seconds": round(verification_seconds, 3),
            "total_seconds": round(perf_counter() - total_started, 3),
        },
    }
