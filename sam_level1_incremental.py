"""Incremental SAM Level 1 synchronization for an already published model instance.

Phase 1 deliberately targets the highest-value/lowest-risk delta first: updates to
existing element names. The reusable ArcadiaOA library is never rewritten. The
baseline instance is adopted once by mapping stable MBSE-App node IDs to SAM IDs;
that mapping is persisted in the model graph metadata by the web adapter.

Structural changes (create/delete nodes, relationship topology, scenarios or
characteristics) are detected before any write and remain blocked until their
incremental handlers are implemented. This keeps the rule strict: never rebuild
or duplicate the complete model merely because one unsupported delta occurred.
"""

from __future__ import annotations

import copy
import hashlib
import json
from time import perf_counter
from typing import Any

from sam_connection import SamSettings
from sam_level1_sync import (
    SamLevel1SyncError,
    _rows,
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

SYNC_STATE_KEY = "sam_sync"
SYNC_STATE_VERSION = 1


def _digest(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scenario_rows(model: dict[str, Any], scenarios: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
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
    return _digest(sorted(_rows(model.get("edges")), key=lambda item: json.dumps(item, sort_keys=True, default=str)))


def _scenario_fingerprint(rows: list[dict[str, Any]]) -> str:
    return _digest(sorted(rows, key=lambda item: json.dumps(item, sort_keys=True, default=str)))


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
    matches = [item for item in _descendants(project, package) if _element_name(item) == name]
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
    """Adopt the already verified immutable snapshot as the incremental baseline."""
    plan = build_level1_sync_plan(model, scenarios=scenarios, project_id=settings.project_id)
    _, _, project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    matches = list(project.find_elements_by_name(str(plan["package_name"])) or [])
    if not matches:
        # The newer managed-direct transport may have returned a different instance
        # package name. Fall back to an unambiguous MBSE_Instance_<model> prefix.
        prefix = "MBSE_Instance_"
        candidates = [
            item
            for item in getattr(project, "environment", []) or []
            if _element_name(item).startswith(prefix)
            and str(plan["model_name"]).replace(" ", "_").lower() in _element_name(item).lower()
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
    """Return a no-write delta plan based on the persisted baseline mapping."""
    state = sync_state_from_model(model)
    current_digest = level1_snapshot_digest(model, scenarios)
    if state is None or state.get("project_id") != settings.project_id:
        return {
            "mode": "baseline_required",
            "supported": True,
            "snapshot_digest": current_digest,
            "counts": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
            "updates": [],
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
                "unchanged": len(_nodes_by_id(model)),
            },
            "updates": [],
            "instance_package_name": state.get("instance_package_name"),
        }

    current_nodes = _nodes_by_id(model)
    previous_nodes = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}
    current_ids = set(current_nodes)
    previous_ids = set(previous_nodes)
    unsupported: list[str] = []
    if current_ids != previous_ids:
        added = sorted(current_ids - previous_ids)
        removed = sorted(previous_ids - current_ids)
        if added:
            unsupported.append("new elements: " + ", ".join(added))
        if removed:
            unsupported.append("removed elements: " + ", ".join(removed))
    if _edge_fingerprint(model) != state.get("edges_fingerprint"):
        unsupported.append("relationship topology or relationship properties changed")
    if _scenario_fingerprint(scenarios) != state.get("scenarios_fingerprint"):
        unsupported.append("operational scenarios changed")

    updates: list[dict[str, Any]] = []
    for node_id in sorted(current_ids & previous_ids):
        current = current_nodes[node_id]
        previous_record = previous_nodes.get(node_id) if isinstance(previous_nodes.get(node_id), dict) else {}
        previous = previous_record.get("source") if isinstance(previous_record.get("source"), dict) else {}
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

    return {
        "mode": "incremental_update",
        "supported": not unsupported,
        "snapshot_digest": current_digest,
        "counts": {
            "create": len(current_ids - previous_ids),
            "update": len(updates),
            "delete": len(previous_ids - current_ids),
            "unchanged": max(0, len(current_ids) - len(updates) - len(current_ids - previous_ids)),
        },
        "updates": updates,
        "unsupported_changes": unsupported,
        "instance_package_name": state.get("instance_package_name"),
    }


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
    """Adopt a baseline, skip no-ops locally, or batch supported UPDATEs."""
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
                "delta": {"create": 0, "update": 0, "delete": 0, "unchanged": len(adopted["nodes"])},
                "timings": {
                    "adoption_seconds": round(perf_counter() - adopt_started, 3),
                    "total_seconds": round(perf_counter() - total_started, 3),
                },
            }
        return {"status": "baseline_required", "sync_state": None}

    plan = build_incremental_plan(model, scenarios=scenarios, settings=settings)
    if expected_digest and expected_digest != plan["snapshot_digest"]:
        raise SamLevel1SyncError(
            "The model changed after the incremental transfer plan was reviewed. Review it again before sending."
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
            "This Level 1 change is structural and is not yet enabled for incremental write. "
            "No SAM data was changed. Unsupported delta: "
            + "; ".join(plan.get("unsupported_changes") or [])
        )

    connect_started = perf_counter()
    connector, _, project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    connection_seconds = perf_counter() - connect_started
    updates = list(plan.get("updates") or [])
    resolved: list[tuple[dict[str, Any], Any]] = []
    for item in updates:
        sam_id = str(item.get("sam_id") or "")
        element = project.find_element_by_id(sam_id) if sam_id else None
        if element is None:
            raise SamLevel1SyncError(
                f"The SAM element mapped to MBSE-App id {item.get('source_id')!r} no longer exists. "
                "No incremental write was performed."
            )
        resolved.append((item, element))

    write_started = perf_counter()
    if resolved:
        project.start_transactional_mode()
        try:
            for item, element in resolved:
                element.name = item["new_name"]
            project.stop_transactional_mode()
        except Exception as exc:
            raise SamLevel1SyncError(f"SAM incremental update transaction failed: {exc}") from exc
    write_seconds = perf_counter() - write_started

    verify_started = perf_counter()
    _, _, verified_project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    for item, _ in resolved:
        current = verified_project.find_element_by_id(str(item.get("sam_id") or ""))
        if current is None or _element_name(current) != item["new_name"]:
            raise SamLevel1SyncError(
                f"SAM accepted the incremental update, but verification failed for {item.get('source_id')!r}."
            )
    verification_seconds = perf_counter() - verify_started

    new_state = copy.deepcopy(state)
    current_nodes = _nodes_by_id(model)
    for item in updates:
        node_id = str(item["source_id"])
        new_state["nodes"][node_id]["name"] = item["new_name"]
        new_state["nodes"][node_id]["source"] = current_nodes[node_id]
    new_state["snapshot_digest"] = plan["snapshot_digest"]
    new_state["edges_fingerprint"] = _edge_fingerprint(model)
    new_state["scenarios_fingerprint"] = _scenario_fingerprint(scenarios)

    return {
        "status": "synced",
        "mode": "incremental_update",
        "sam_write_performed": bool(updates),
        "package_name": state.get("instance_package_name"),
        "sam_package_id": state.get("instance_package_id"),
        "snapshot_digest": plan["snapshot_digest"],
        "sync_state": new_state,
        "delta": plan["counts"],
        "timings": {
            "connection_seconds": round(connection_seconds, 3),
            "write_seconds": round(write_seconds, 3),
            "verification_seconds": round(verification_seconds, 3),
            "total_seconds": round(perf_counter() - total_started, 3),
        },
    }
