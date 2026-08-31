"""Complete Level 1 incremental relationship support for the Operational Analysis PoC.

This layer closes the remaining ArcadiaOA relationship strategies while keeping the
known SAM nesting limitation explicit. The Companion App Level 1 model remains the
semantic source of truth for nested usage when SAM flattens ownership.
"""
from __future__ import annotations

import copy
from time import perf_counter
from typing import Any

from arcadia_oa_library import DEFAULT_ARCADIA_OA_LIBRARY
from exchange_transport import relationship_identity
from sam_connection import SamSettings
from sam_level1_direct import _MetadataTolerantFactory
from sam_level1_incremental import (
    _delete_owned_tree,
    _descendants,
    _edge_fingerprint,
    _managed_instance,
    _nodes_by_id,
    _other_edge_fingerprint,
    _relationship_name,
)
from sam_level1_managed_direct import _library_status
from sam_level1_scenario_incremental import (
    build_incremental_plan_with_scenarios,
    sync_level1_incremental_with_scenarios,
)
from sam_level1_sync import (
    SamLevel1SyncError,
    _documentation,
    _rows,
    _source_document,
    level1_snapshot_digest,
)
from sam_level1_transactional import _element_id, _element_name, _load_project
from sam_reload_safe_factory import ReloadSafeFactory

COMPLETE_RELATIONSHIP_TRACKING_REVISION = 1
SCENARIO_STRUCTURE_REVISION = 1
REMAINING_RELATIONSHIP_TYPES = frozenset(
    {"CONTAINS", "DECOMPOSES", "PERFORMS", "SUPPORTS_CAPABILITY", "LOCATED_IN"}
)


def _edge_rows(model: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(edge)
        for edge in _rows(model.get("edges"))
        if str(edge.get("type") or "") in REMAINING_RELATIONSHIP_TYPES
    ]


def _fingerprint(model: dict[str, Any]) -> str:
    return _edge_fingerprint({"edges": _edge_rows(model)})


def _edges_by_id(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for edge in _edge_rows(model):
        identity = relationship_identity(edge)
        if identity in result:
            raise SamLevel1SyncError(f"Relationship identity {identity!r} is duplicated.")
        result[identity] = edge
    return result


def _mapping(edge: dict[str, Any]) -> dict[str, Any]:
    relation = str(edge.get("type") or "")
    mapping = DEFAULT_ARCADIA_OA_LIBRARY.contract.get("relationships", {}).get(relation)
    if not isinstance(mapping, dict):
        raise SamLevel1SyncError(f"No ArcadiaOA mapping exists for {relation!r}.")
    return mapping


def _strategy(edge: dict[str, Any]) -> str:
    return str(_mapping(edge).get("strategy") or "")


def _ref_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        raw = value.get("id") or value.get("_id")
        return str(raw).strip() if raw is not None and str(raw).strip() else None
    return _element_id(value)


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return [value]


def _contains_id(value: Any, expected: str) -> bool:
    return any(_ref_id(item) == expected for item in _items(value))


def _owner_id(element: Any) -> str | None:
    return _ref_id(getattr(element, "owner", None))


def _node_sam_ids(state: dict[str, Any]) -> dict[str, str]:
    records = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}
    return {
        str(node_id): str(record["sam_id"])
        for node_id, record in records.items()
        if isinstance(record, dict) and record.get("sam_id")
    }


def _record(edge: dict[str, Any], sam_id: str | None) -> dict[str, Any]:
    return {
        "sam_id": sam_id,
        "type": str(edge.get("type") or ""),
        "strategy": _strategy(edge),
        "source_id": str(edge.get("source") or ""),
        "target_id": str(edge.get("target") or ""),
        "key": edge.get("key", 0),
        "name": _relationship_name(edge),
        "source": copy.deepcopy(edge),
    }


def _match_existing(
    descendants: list[Any], edge: dict[str, Any], node_ids: dict[str, str]
) -> Any | None:
    strategy = _strategy(edge)
    if strategy == "nested_usage":
        return None
    source_id = node_ids.get(str(edge.get("source") or ""))
    target_id = node_ids.get(str(edge.get("target") or ""))
    if not source_id or not target_id:
        raise SamLevel1SyncError(
            f"Relationship {_relationship_name(edge)!r} has an unmapped endpoint."
        )
    matches: list[Any] = []
    for item in descendants:
        if strategy == "perform":
            if _owner_id(item) == source_id and _contains_id(
                getattr(item, "performed_action", None), target_id
            ):
                matches.append(item)
        elif strategy == "allocation":
            mapping = _mapping(edge)
            from_local = str(edge.get(str(mapping.get("from_endpoint") or "source")) or "")
            to_local = str(edge.get(str(mapping.get("to_endpoint") or "target")) or "")
            from_id, to_id = node_ids.get(from_local), node_ids.get(to_local)
            if (
                from_id
                and to_id
                and _contains_id(getattr(item, "source", None), from_id)
                and _contains_id(getattr(item, "target", None), to_id)
            ):
                matches.append(item)
        elif strategy == "reference":
            mapping = _mapping(edge)
            owner_local = str(edge.get(str(mapping.get("owner_endpoint") or "source")) or "")
            ref_local = str(edge.get(str(mapping.get("referenced_endpoint") or "target")) or "")
            owner_expected, ref_expected = node_ids.get(owner_local), node_ids.get(ref_local)
            if (
                owner_expected
                and ref_expected
                and _owner_id(item) == owner_expected
                and _contains_id(getattr(item, "referenced_feature", None), ref_expected)
            ):
                matches.append(item)
    if len(matches) == 1:
        return matches[0]
    by_name = [item for item in descendants if _element_name(item) == _relationship_name(edge)]
    if len(by_name) == 1:
        return by_name[0]
    if matches:
        raise SamLevel1SyncError(
            f"Cannot uniquely adopt relationship {_relationship_name(edge)!r}: "
            f"found {len(matches)} semantic matches."
        )
    return None


def enrich_state_with_remaining_relationships(
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
    """Read-only adoption of all remaining Level 1 relationship strategies."""
    if (
        int(state.get("complete_relationship_tracking_revision", 0) or 0)
        == COMPLETE_RELATIONSHIP_TRACKING_REVISION
    ):
        return copy.deepcopy(state)
    expected = state.get("unhandled_edges_fingerprint")
    if require_migration_proof and expected is not None and _fingerprint(model) != expected:
        raise SamLevel1SyncError(
            "The manifest predates complete relationship tracking and one of "
            "CONTAINS/DECOMPOSES/PERFORMS/SUPPORTS_CAPABILITY/LOCATED_IN already changed. "
            "No SAM write was performed."
        )
    _, _, project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    package = _managed_instance(project, state)
    descendants = _descendants(project, package)
    node_ids = _node_sam_ids(state)
    records: dict[str, dict[str, Any]] = {}
    for identity, edge in _edges_by_id(model).items():
        if _strategy(edge) == "nested_usage":
            record = _record(edge, None)
            mapping = _mapping(edge)
            parent_local = str(edge.get(str(mapping.get("parent_endpoint") or "source")) or "")
            child_local = str(edge.get(str(mapping.get("child_endpoint") or "target")) or "")
            child = project.find_element_by_id(str(node_ids.get(child_local) or ""))
            record["owner_expected"] = node_ids.get(parent_local)
            record["owner_observed"] = _owner_id(child) if child is not None else None
            records[identity] = record
            continue
        element = _match_existing(descendants, edge, node_ids)
        if element is None:
            raise SamLevel1SyncError(
                f"Cannot adopt existing relationship {_relationship_name(edge)!r} in SAM."
            )
        sam_id = _element_id(element)
        if not sam_id:
            raise SamLevel1SyncError(
                f"Relationship {_relationship_name(edge)!r} has no stable SAM ID."
            )
        records[identity] = _record(edge, sam_id)
    result = copy.deepcopy(state)
    result["remaining_relationships"] = records
    result["complete_relationship_tracking_revision"] = COMPLETE_RELATIONSHIP_TRACKING_REVISION
    result["unhandled_edges_fingerprint"] = _fingerprint(model)
    return result


def remaining_relationship_change_set(
    model: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    current = _edges_by_id(model)
    previous = (
        state.get("remaining_relationships")
        if isinstance(state.get("remaining_relationships"), dict)
        else {}
    )
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
        new = current[rid]
        if old == new:
            unchanged += 1
            continue
        old_shape, new_shape = copy.deepcopy(old), copy.deepcopy(new)
        old_shape.pop("name", None)
        new_shape.pop("name", None)
        if old_shape != new_shape:
            raise SamLevel1SyncError(
                f"Relationship {_relationship_name(new)!r} changed non-name properties "
                "without changing its structural identity."
            )
        updates.append(
            {
                "relationship_id": rid,
                "sam_id": record.get("sam_id"),
                "old_name": str(record.get("name") or _relationship_name(old)),
                "new_name": _relationship_name(new),
                "old_edge": copy.deepcopy(old),
                "edge": copy.deepcopy(new),
            }
        )
    return {
        "create": creates,
        "update": updates,
        "delete": deletes,
        "counts": {
            "create": len(creates),
            "update": len(updates),
            "delete": len(deletes),
            "unchanged": unchanged,
        },
    }


def _shadow_for_complete_plan(model: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(model)
    shadow = copy.deepcopy(state)
    shadow["unhandled_edges_fingerprint"] = _fingerprint(model)
    if int(shadow.get("scenario_structure_revision", 0) or 0) != SCENARIO_STRUCTURE_REVISION:
        records = shadow.get("scenarios") if isinstance(shadow.get("scenarios"), dict) else {}
        for record in records.values():
            if isinstance(record, dict) and isinstance(record.get("source"), dict):
                record["source"] = copy.deepcopy(record["source"])
                record["source"]["__sam_structure_revision"] = 0
    value.setdefault("graph", {})["sam_sync"] = shadow
    return value


def build_incremental_plan_complete(
    model: dict[str, Any], *, scenarios: list[dict[str, Any]], settings: SamSettings
) -> dict[str, Any]:
    state = model.get("graph", {}).get("sam_sync") if isinstance(model.get("graph"), dict) else None
    if not isinstance(state, dict):
        return build_incremental_plan_with_scenarios(model, scenarios=scenarios, settings=settings)
    if (
        int(state.get("complete_relationship_tracking_revision", 0) or 0)
        != COMPLETE_RELATIONSHIP_TRACKING_REVISION
    ):
        raise SamLevel1SyncError("Complete relationship tracking state is not prepared.")
    base = build_incremental_plan_with_scenarios(
        _shadow_for_complete_plan(model, state), scenarios=scenarios, settings=settings
    )
    remaining = remaining_relationship_change_set(model, state)
    unsupported = list(base.get("unsupported_changes") or [])
    base_rel = base.get("relationship_counts") or {}
    counts = {
        "create": int(base_rel.get("create") or 0) + remaining["counts"]["create"],
        "update": int(base_rel.get("update") or 0) + remaining["counts"]["update"],
        "delete": int(base_rel.get("delete") or 0) + remaining["counts"]["delete"],
        "unchanged": int(base_rel.get("unchanged") or 0) + remaining["counts"]["unchanged"],
    }
    creates = list(base.get("relationship_creates") or []) + remaining["create"]
    updates = list(base.get("relationship_updates") or []) + remaining["update"]
    deletes = list(base.get("relationship_deletes") or []) + remaining["delete"]
    has_remaining = any(remaining["counts"][key] for key in ("create", "update", "delete"))
    node_counts = base.get("counts") or {}
    scenario_counts = base.get("scenario_counts") or {}
    has_nodes = any(int(node_counts.get(key) or 0) for key in ("create", "update", "delete"))
    has_scenarios = any(
        int(scenario_counts.get(key) or 0) for key in ("create", "update", "delete")
    )
    has_lower_relationship = any(
        int(base_rel.get(key) or 0) for key in ("create", "update", "delete")
    )
    if has_remaining and (has_nodes or has_scenarios or has_lower_relationship):
        unsupported.append(
            "CONTAINS/DECOMPOSES/PERFORMS/SUPPORTS_CAPABILITY/LOCATED_IN changes "
            "must be synchronized separately from node, Operational Exchange, "
            "Communication Mean, or Operational Scenario changes in this PoC increment"
        )
    unsupported = list(dict.fromkeys(unsupported))
    result = dict(base)
    result.update(
        {
            "mode": (
                "incremental_noop"
                if not has_remaining
                and not has_nodes
                and not has_scenarios
                and not has_lower_relationship
                and not unsupported
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


def _default_owner(project: Any, package: Any, node: dict[str, Any]) -> Any:
    node_type = str(node.get("type") or "")
    if node_type in {"OperationalEntity", "OperationalActor"}:
        name = "oa_operationalContext"
    elif node_type == "OperationalActivity":
        name = "oa_operationalBehavior"
    else:
        return package
    matches = [item for item in _descendants(project, package) if _element_name(item) == name]
    if len(matches) != 1:
        raise SamLevel1SyncError(f"Cannot resolve default SAM owner {name!r}.")
    return matches[0]


def _create_relationship(
    factory: Any,
    project: Any,
    package: Any,
    edge: dict[str, Any],
    node_ids: dict[str, str],
    definitions: dict[str, Any],
) -> Any:
    strategy = _strategy(edge)
    source = project.find_element_by_id(node_ids[str(edge.get("source") or "")])
    target = project.find_element_by_id(node_ids[str(edge.get("target") or "")])
    if source is None or target is None:
        raise SamLevel1SyncError(
            f"Relationship {_relationship_name(edge)!r} endpoint disappeared before CREATE."
        )
    name = _relationship_name(edge)
    if strategy == "perform":
        return factory.create_perform_action_usage(
            name=name, owner=source, performed_action=target
        )
    if strategy == "allocation":
        mapping = _mapping(edge)
        from_local = str(edge.get(str(mapping.get("from_endpoint") or "source")) or "")
        to_local = str(edge.get(str(mapping.get("to_endpoint") or "target")) or "")
        from_element = project.find_element_by_id(node_ids[from_local])
        to_element = project.find_element_by_id(node_ids[to_local])
        return factory.create_allocation_usage(
            name=name,
            owner=package,
            source=[from_element],
            target=[to_element],
            source_feature=from_element,
            target_feature=[to_element],
            related_feature=[from_element, to_element],
            is_directed=True,
        )
    if strategy == "reference":
        mapping = _mapping(edge)
        owner_local = str(edge.get(str(mapping.get("owner_endpoint") or "source")) or "")
        ref_local = str(edge.get(str(mapping.get("referenced_endpoint") or "target")) or "")
        owner = project.find_element_by_id(node_ids[owner_local])
        referenced = project.find_element_by_id(node_ids[ref_local])
        return factory.create_reference_usage(
            name=name,
            owner=owner,
            reference_type=[definitions["OperationalEntity"]],
            type_=[definitions["OperationalEntity"]],
            referenced_feature=[referenced],
        )
    raise SamLevel1SyncError(f"Unsupported CREATE strategy {strategy!r}.")


def _remaining_only(plan: dict[str, Any]) -> tuple[list, list, list]:
    def pick(items):
        return [
            item
            for item in items
            if isinstance(item.get("edge"), dict)
            and str(item["edge"].get("type") or "") in REMAINING_RELATIONSHIP_TYPES
        ]
    return (
        pick(plan.get("relationship_creates") or []),
        pick(plan.get("relationship_updates") or []),
        pick(plan.get("relationship_deletes") or []),
    )


def sync_level1_incremental_complete(
    model: dict[str, Any],
    *,
    scenarios: list[dict[str, Any]],
    settings: SamSettings,
    expected_digest: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    state = model.get("graph", {}).get("sam_sync") if isinstance(model.get("graph"), dict) else None
    if not isinstance(state, dict):
        raise SamLevel1SyncError("Incremental SAM state is missing.")
    shadow_model = _shadow_for_complete_plan(model, state)
    plan = build_incremental_plan_complete(model, scenarios=scenarios, settings=settings)
    if expected_digest and expected_digest != plan.get("snapshot_digest"):
        raise SamLevel1SyncError(
            "The model changed after the reviewed Level 1 change set was prepared."
        )
    if not plan.get("supported"):
        raise SamLevel1SyncError("; ".join(plan.get("unsupported_changes") or []))
    creates, updates, deletes = _remaining_only(plan)
    if not (creates or updates or deletes):
        result = sync_level1_incremental_with_scenarios(
            shadow_model,
            scenarios=scenarios,
            settings=settings,
            expected_digest=expected_digest,
            connector_class=connector_class,
            project_manager_class=project_manager_class,
            factory_class=factory_class,
        )
        if isinstance(result.get("sync_state"), dict):
            result["sync_state"]["scenario_structure_revision"] = SCENARIO_STRUCTURE_REVISION
            result["sync_state"]["complete_relationship_tracking_revision"] = (
                COMPLETE_RELATIONSHIP_TRACKING_REVISION
            )
            result["sync_state"]["unhandled_edges_fingerprint"] = _fingerprint(model)
        if result.get("mode") == "incremental_scenario_change_set":
            result["mode"] = "incremental_change_set"
        return result

    connector, _, project, resolved_factory = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    package = _managed_instance(project, state)
    library = _library_status(project)
    if not library.get("loaded"):
        raise SamLevel1SyncError("The reusable ArcadiaOA library is incomplete.")
    factory = _MetadataTolerantFactory(
        ReloadSafeFactory(project, resolved_factory(project, connector))
    )
    node_ids = _node_sam_ids(state)
    nodes = _nodes_by_id(model)
    previous_nodes = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}
    created_records: dict[str, str | None] = {}
    warnings: list[str] = []
    write_started = perf_counter()
    project.start_transactional_mode()
    try:
        for item in deletes:
            edge = item.get("edge") if isinstance(item.get("edge"), dict) else {}
            if _strategy(edge) != "nested_usage":
                continue
            mapping = _mapping(edge)
            child_local = str(edge.get(str(mapping.get("child_endpoint") or "target")) or "")
            child_sam = node_ids.get(child_local) or str(
                (previous_nodes.get(child_local) or {}).get("sam_id") or ""
            )
            child = project.find_element_by_id(child_sam)
            node = nodes.get(child_local) or (previous_nodes.get(child_local) or {}).get("source") or {}
            if child is None:
                raise SamLevel1SyncError("Nested relationship child disappeared before DELETE.")
            child.owner = _default_owner(project, package, node)

        for item in creates:
            edge = item.get("edge") if isinstance(item.get("edge"), dict) else {}
            rid = str(item.get("relationship_id") or "")
            if _strategy(edge) == "nested_usage":
                mapping = _mapping(edge)
                parent_local = str(edge.get(str(mapping.get("parent_endpoint") or "source")) or "")
                child_local = str(edge.get(str(mapping.get("child_endpoint") or "target")) or "")
                parent = project.find_element_by_id(node_ids[parent_local])
                child = project.find_element_by_id(node_ids[child_local])
                if parent is None or child is None:
                    raise SamLevel1SyncError("Nested relationship endpoint disappeared before CREATE.")
                child.owner = parent
                created_records[rid] = None
                continue
            element = _create_relationship(
                factory, project, package, edge, node_ids, library["definitions"]
            )
            _documentation(factory, element, _source_document(edge, "relationship"))
            created_records[rid] = _element_id(element)

        for item in updates:
            edge = item.get("edge") if isinstance(item.get("edge"), dict) else {}
            if _strategy(edge) == "nested_usage":
                continue
            element = project.find_element_by_id(str(item.get("sam_id") or ""))
            if element is None:
                raise SamLevel1SyncError("Relationship UPDATE target disappeared.")
            element.name = item["new_name"]

        for item in deletes:
            edge = item.get("edge") if isinstance(item.get("edge"), dict) else {}
            if _strategy(edge) == "nested_usage":
                continue
            element = project.find_element_by_id(str(item.get("sam_id") or ""))
            if element is None:
                raise SamLevel1SyncError("Relationship DELETE target disappeared.")
            _delete_owned_tree(element, project)
        project.stop_transactional_mode()
    except Exception as exc:
        raise SamLevel1SyncError(
            f"SAM complete-relationship transaction failed: {exc}"
        ) from exc
    write_seconds = perf_counter() - write_started

    _, _, verified, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=resolved_factory,
    )
    for item in creates:
        edge = item.get("edge") if isinstance(item.get("edge"), dict) else {}
        rid = str(item.get("relationship_id") or "")
        if _strategy(edge) == "nested_usage":
            mapping = _mapping(edge)
            child_local = str(edge.get(str(mapping.get("child_endpoint") or "target")) or "")
            parent_local = str(edge.get(str(mapping.get("parent_endpoint") or "source")) or "")
            child = verified.find_element_by_id(node_ids[child_local])
            observed = _owner_id(child) if child is not None else None
            expected_owner = node_ids[parent_local]
            if observed and observed != expected_owner:
                warnings.append(
                    f"SAM flattened nested relationship {_relationship_name(edge)!r}; "
                    "the Companion App Level 1 model remains authoritative."
                )
            continue
        current = verified.find_element_by_id(str(created_records.get(rid) or ""))
        if current is None:
            raise SamLevel1SyncError(
                f"Relationship CREATE verification failed for {_relationship_name(edge)!r}."
            )
    for item in updates:
        edge = item.get("edge") if isinstance(item.get("edge"), dict) else {}
        if _strategy(edge) == "nested_usage":
            continue
        current = verified.find_element_by_id(str(item.get("sam_id") or ""))
        if current is None or _element_name(current) != item["new_name"]:
            raise SamLevel1SyncError(
                f"Relationship UPDATE verification failed for {_relationship_name(edge)!r}."
            )
    for item in deletes:
        edge = item.get("edge") if isinstance(item.get("edge"), dict) else {}
        if _strategy(edge) != "nested_usage" and verified.find_element_by_id(
            str(item.get("sam_id") or "")
        ) is not None:
            raise SamLevel1SyncError(
                f"Relationship DELETE verification failed for {_relationship_name(edge)!r}."
            )

    current_edges = _edges_by_id(model)
    records = (
        copy.deepcopy(state.get("remaining_relationships"))
        if isinstance(state.get("remaining_relationships"), dict)
        else {}
    )
    for item in deletes:
        records.pop(str(item.get("relationship_id") or ""), None)
    for rid, edge in current_edges.items():
        if rid in created_records:
            records[rid] = _record(edge, created_records[rid])
        elif isinstance(records.get(rid), dict):
            records[rid] = _record(edge, records[rid].get("sam_id"))
    new_state = copy.deepcopy(state)
    new_state["remaining_relationships"] = records
    new_state["complete_relationship_tracking_revision"] = COMPLETE_RELATIONSHIP_TRACKING_REVISION
    new_state["unhandled_edges_fingerprint"] = _fingerprint(model)
    new_state["other_edges_fingerprint"] = _other_edge_fingerprint(model)
    new_state["snapshot_digest"] = level1_snapshot_digest(model, scenarios)
    return {
        **plan,
        "status": "synced",
        "mode": "incremental_change_set",
        "sam_write_performed": True,
        "sync_state": new_state,
        "metadata_warnings": warnings + list(getattr(factory, "warnings", []) or []),
        "timings": {
            "write_seconds": round(write_seconds, 3),
            "total_seconds": round(perf_counter() - started, 3),
        },
    }
