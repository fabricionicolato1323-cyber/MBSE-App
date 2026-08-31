"""Incremental SAM Level 1 synchronization for one managed model instance.

The reusable ArcadiaOA library is never rewritten after it is available. A verified
local manifest maps stable MBSE-App node IDs to SAM IDs and provides the baseline
for an explicit, user-reviewed change set.

Supported in this stage:
* no-op detection without a SAM write;
* name-only UPDATEs of existing nodes;
* CREATE of new nodes when relationship/scenario topology is unchanged; and
* DELETE of existing nodes when relationship/scenario topology is unchanged.

Relationship/scenario deltas are deliberately detected and block the entire write
until their own incremental handlers are enabled. The writer never performs a
partial structural synchronization or rebuilds the complete instance silently.
"""

from __future__ import annotations

import copy
import hashlib
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

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
    _children,
    _element_id,
    _element_name,
    _load_project,
)
from sam_reload_safe_factory import ReloadSafeFactory

SYNC_STATE_KEY = "sam_sync"
SYNC_STATE_VERSION = 1


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
    if not isinstance(state, dict) or state.get("version") != SYNC_STATE_VERSION:
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


def _edge_fingerprint(model: dict[str, Any]) -> str:
    return _digest(
        sorted(
            _rows(model.get("edges")),
            key=lambda item: json.dumps(item, sort_keys=True, default=str),
        )
    )


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


def _build_state(
    model: dict[str, Any],
    scenarios: list[dict[str, Any]],
    *,
    settings: SamSettings,
    package_name: str,
    package_id: str | None,
    node_elements: dict[str, Any],
) -> dict[str, Any]:
    nodes = _nodes_by_id(model)
    return {
        "version": SYNC_STATE_VERSION,
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
        "edges_fingerprint": _edge_fingerprint(model),
        "scenarios_fingerprint": _scenario_fingerprint(scenarios),
    }


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
    return _build_state(
        model,
        scenarios,
        settings=settings,
        package_name=_element_name(package),
        package_id=_element_id(package),
        node_elements=node_elements,
    )


def build_incremental_plan(
    model: dict[str, Any],
    *,
    scenarios: list[dict[str, Any]],
    settings: SamSettings,
) -> dict[str, Any]:
    """Return a read-only node change set based on the persisted SAM baseline."""
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
            "reason": "No incremental baseline is recorded for this SAM project yet.",
        }
    if current_digest == state.get("snapshot_digest"):
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
            "unsupported_changes": [],
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
    relationship_changed = _edge_fingerprint(model) != state.get("edges_fingerprint")
    scenarios_changed = (
        _scenario_fingerprint(scenarios) != state.get("scenarios_fingerprint")
    )
    if relationship_changed:
        unsupported.append(
            "relationship topology or relationship properties changed; relationship incremental sync is pending"
        )
    if scenarios_changed:
        unsupported.append(
            "operational scenarios changed; scenario incremental sync is pending"
        )

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

    unchanged = max(0, len(current_ids & previous_ids) - len(updates))
    mode = (
        "incremental_noop"
        if not creates and not updates and not deletes and not unsupported
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
        "relationship_changes_pending": relationship_changed,
        "scenario_changes_pending": scenarios_changed,
        "unsupported_changes": unsupported,
        "instance_package_name": state.get("instance_package_name"),
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
    """Adopt a baseline, skip no-ops, or apply one reviewed node change set."""
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

    # Resolve every existing write target before the first write. This prevents a
    # stale manifest from producing a partial change set.
    for item in updates + deletes:
        sam_id = str(item.get("sam_id") or "")
        element = project.find_element_by_id(sam_id) if sam_id else None
        if element is None:
            raise SamLevel1SyncError(
                f"The SAM element mapped to MBSE-App id {item.get('source_id')!r} no longer exists. "
                "No incremental write was performed."
            )

    write_started = perf_counter()
    staged, metadata_warnings = _stage_incremental_creates(
        connector,
        project,
        resolved_factory,
        state,
        creates,
    )

    # Direct CREATE is staged with temporary names because PySAM 0.3.1 direct
    # creation is the reliable server path. Once all new objects exist, updates,
    # deletions and publication renames are committed together as modifications
    # of already-persisted IDs.
    if updates or deletes or staged:
        try:
            project.start_transactional_mode()
            for item in updates:
                element = project.find_element_by_id(str(item.get("sam_id") or ""))
                if element is None:
                    raise SamLevel1SyncError(
                        f"SAM update target {item.get('source_id')!r} disappeared before commit."
                    )
                element.name = item["new_name"]
            for item in staged:
                element = project.find_element_by_id(str(item.get("sam_id") or ""))
                if element is None:
                    raise SamLevel1SyncError(
                        f"Staged SAM element {item.get('source_id')!r} disappeared before publication."
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
    for item in staged:
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
    verification_seconds = perf_counter() - verify_started

    new_state = copy.deepcopy(state)
    current_nodes = _nodes_by_id(model)
    for item in updates:
        node_id = str(item["source_id"])
        new_state["nodes"][node_id]["name"] = item["new_name"]
        new_state["nodes"][node_id]["source"] = current_nodes[node_id]
    for item in staged:
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
    new_state["snapshot_digest"] = plan["snapshot_digest"]
    new_state["edges_fingerprint"] = _edge_fingerprint(model)
    new_state["scenarios_fingerprint"] = _scenario_fingerprint(scenarios)

    return {
        "status": "synced",
        "mode": "incremental_change_set",
        "sam_write_performed": bool(updates or creates or deletes),
        "package_name": state.get("instance_package_name"),
        "sam_package_id": state.get("instance_package_id"),
        "snapshot_digest": plan["snapshot_digest"],
        "sync_state": new_state,
        "delta": plan["counts"],
        "metadata_warnings": metadata_warnings,
        "timings": {
            "connection_seconds": round(connection_seconds, 3),
            "write_seconds": round(write_seconds, 3),
            "verification_seconds": round(verification_seconds, 3),
            "total_seconds": round(perf_counter() - total_started, 3),
        },
    }
