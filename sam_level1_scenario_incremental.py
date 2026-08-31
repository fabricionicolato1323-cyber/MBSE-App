"""Level 1D incremental Operational Scenario synchronization."""
from __future__ import annotations

import copy
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

from sam_connection import SamSettings
from sam_level1_communication_incremental import (
    build_incremental_plan_with_communication,
    sync_level1_incremental_with_communication,
)
from sam_level1_direct import _MetadataTolerantFactory
from sam_level1_incremental import (
    SYNC_STATE_VERSION,
    _delete_owned_tree,
    _descendants,
    _managed_instance,
    _scenario_fingerprint,
)
from sam_level1_managed_direct import _library_status
from sam_level1_sync import SamLevel1SyncError, _documentation, _rows, level1_snapshot_digest
from sam_level1_transactional import _element_id, _element_name, _load_project
from sam_reload_safe_factory import ReloadSafeFactory

SCENARIO_TRACKING_REVISION = 1


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def scenario_identity(row: dict[str, Any]) -> str:
    value = _clean(row.get("id"))
    if value:
        return f"id:{value}"
    value = _clean(row.get("name")).casefold()
    if value:
        return f"name:{value}"
    raise SamLevel1SyncError("Operational Scenario has no stable id or name.")


def _source(row: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(row)
    value.pop("valid", None)
    value.pop("issues", None)
    return value


def _valid(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [copy.deepcopy(x) for x in rows if isinstance(x, dict) and x.get("valid") is not False]


def _by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in _valid(rows):
        key = scenario_identity(row)
        if key in result:
            raise SamLevel1SyncError(f"Duplicate Operational Scenario identity {key!r}.")
        result[key] = row
    return result


def _record(row: dict[str, Any], sam_id: str) -> dict[str, Any]:
    return {
        "sam_id": sam_id,
        "name": _clean(row.get("name") or row.get("id") or "Operational Scenario"),
        "source": _source(row),
    }


def enrich_state_with_current_scenarios(
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
    """Read-only adoption of existing scenario SAM IDs."""
    if int(state.get("scenario_tracking_revision", 0) or 0) == SCENARIO_TRACKING_REVISION:
        return copy.deepcopy(state)
    if int(state.get("version", 0) or 0) != SYNC_STATE_VERSION:
        raise SamLevel1SyncError("Operational Scenario tracking requires a v2 SAM manifest.")

    _, _, project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    package = _managed_instance(project, state)
    descendants = _descendants(project, package)
    current = _by_id(scenarios)
    mapped: dict[str, Any] = {}
    missing: set[str] = set()
    for key, row in current.items():
        name = _clean(row.get("name") or row.get("id") or "Operational Scenario")
        matches = [x for x in descendants if _element_name(x) == name]
        if not matches:
            missing.add(key)
            continue
        if len(matches) != 1:
            raise SamLevel1SyncError(
                f"Cannot adopt Operational Scenario {name!r}: found {len(matches)} SAM matches."
            )
        mapped[key] = matches[0]

    if _scenario_fingerprint(_valid(scenarios)) != state.get("scenarios_fingerprint"):
        previous = [row for key, row in current.items() if key not in missing]
        if require_migration_proof and _scenario_fingerprint(previous) != state.get("scenarios_fingerprint"):
            raise SamLevel1SyncError(
                "The old manifest predates scenario tracking and this scenario change is not "
                "provably additive. No SAM data was changed."
            )

    result = copy.deepcopy(state)
    result["scenarios"] = {}
    for key, element in mapped.items():
        sam_id = _element_id(element)
        if not sam_id:
            raise SamLevel1SyncError(f"Operational Scenario {_element_name(element)!r} has no SAM ID.")
        result["scenarios"][key] = _record(current[key], sam_id)
    result["scenario_tracking_revision"] = SCENARIO_TRACKING_REVISION
    return result


def scenario_change_set(
    scenarios: list[dict[str, Any]], state: dict[str, Any]
) -> dict[str, Any]:
    current = _by_id(scenarios)
    previous = state.get("scenarios") if isinstance(state.get("scenarios"), dict) else {}
    cids, pids = set(current), set(previous)
    creates = [{"scenario_id": k, "scenario": current[k]} for k in sorted(cids - pids)]
    deletes = [
        {
            "scenario_id": k,
            "sam_id": (previous.get(k) or {}).get("sam_id"),
            "old_name": str((previous.get(k) or {}).get("name") or ""),
            "old_scenario": copy.deepcopy((previous.get(k) or {}).get("source") or {}),
        }
        for k in sorted(pids - cids)
    ]
    updates, unchanged = [], 0
    for key in sorted(cids & pids):
        record = previous.get(key) if isinstance(previous.get(key), dict) else {}
        old = record.get("source") if isinstance(record.get("source"), dict) else {}
        new = _source(current[key])
        if old == new:
            unchanged += 1
            continue
        a, b = copy.deepcopy(old), copy.deepcopy(new)
        a.pop("name", None)
        b.pop("name", None)
        updates.append(
            {
                "scenario_id": key,
                "sam_id": record.get("sam_id"),
                "old_name": str(record.get("name") or old.get("name") or ""),
                "new_name": _clean(new.get("name") or new.get("id") or "Operational Scenario"),
                "change_kind": "rename" if a == b else "replace",
                "old_scenario": old,
                "scenario": current[key],
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


def _shadow(model: dict[str, Any], state: dict[str, Any], scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    value = copy.deepcopy(model)
    shadow = copy.deepcopy(state)
    shadow["scenarios_fingerprint"] = _scenario_fingerprint(_valid(scenarios))
    value.setdefault("graph", {})["sam_sync"] = shadow
    return value


def build_incremental_plan_with_scenarios(
    model: dict[str, Any], *, scenarios: list[dict[str, Any]], settings: SamSettings
) -> dict[str, Any]:
    state = model.get("graph", {}).get("sam_sync") if isinstance(model.get("graph"), dict) else None
    if not isinstance(state, dict):
        return build_incremental_plan_with_communication(model, scenarios=scenarios, settings=settings)
    if int(state.get("scenario_tracking_revision", 0) or 0) != SCENARIO_TRACKING_REVISION:
        raise SamLevel1SyncError("Operational Scenario tracking state is not prepared.")

    base = build_incremental_plan_with_communication(
        _shadow(model, state, scenarios), scenarios=scenarios, settings=settings
    )
    delta = scenario_change_set(scenarios, state)
    unsupported = list(base.get("unsupported_changes") or [])
    has_scenario = any(delta["counts"][k] for k in ("create", "update", "delete"))
    has_nodes = any(int((base.get("counts") or {}).get(k) or 0) for k in ("create", "update", "delete"))
    has_rel = any(int((base.get("relationship_counts") or {}).get(k) or 0) for k in ("create", "update", "delete"))
    if has_scenario and (has_nodes or has_rel):
        unsupported.append(
            "Operational Scenario changes must be synchronized separately from node or relationship changes"
        )
    unsupported = list(dict.fromkeys(unsupported))
    result = dict(base)
    result.update(
        {
            "mode": "incremental_change_set" if has_scenario or has_nodes or has_rel else "incremental_noop",
            "supported": not unsupported,
            "scenario_counts": delta["counts"],
            "scenario_creates": delta["create"],
            "scenario_updates": delta["update"],
            "scenario_deletes": delta["delete"],
            "scenario_changes_pending": bool(unsupported),
            "unsupported_changes": unsupported,
        }
    )
    return result


def _activity_names(model: dict[str, Any]) -> dict[str, str]:
    return {
        str(x.get("id")): _clean(x.get("name") or x.get("id"))
        for x in _rows(model.get("nodes"))
        if x.get("id") is not None and str(x.get("type") or "") == "OperationalActivity"
    }


def _create_tree(factory: Any, package: Any, definitions: dict[str, Any], model: dict[str, Any],
                 scenario: dict[str, Any], staging_name: str) -> dict[str, Any]:
    root = factory.create_action_usage(
        name=staging_name,
        owner=package,
        action_definition=[definitions["OperationalScenario"]],
    )
    _documentation(factory, root, json.dumps(_source(scenario), ensure_ascii=False, sort_keys=True, default=str))
    names = _activity_names(model)
    steps = [x for x in _rows(scenario.get("steps")) if x.get("kind") in {"activity", "interaction"}]
    by_pos, actions, expected = {}, [], []

    for pos, step in enumerate(steps, 1):
        if step.get("kind") != "activity":
            continue
        aid = str(step.get("activity_id") or "")
        label = f"{pos}. {names.get(aid, aid or 'Activity')}"
        action = factory.create_action_usage(
            name=label, owner=root, action_definition=[definitions["OperationalActivity"]]
        )
        _documentation(factory, action, json.dumps(
            {"scenario_step": pos, "kind": "activity", "activity_id": aid},
            ensure_ascii=False, sort_keys=True
        ))
        by_pos[pos] = action
        actions.append(action)
        expected.append(label)

    for pos, step in enumerate(steps, 1):
        if step.get("kind") != "interaction":
            continue
        before, after = by_pos.get(pos - 1), by_pos.get(pos + 1)
        if before is None or after is None:
            raise SamLevel1SyncError(
                f"Scenario {_clean(scenario.get('name'))!r} has an interaction without adjacent activities."
            )
        label = f"{pos}. {_clean(step.get('exchange_name') or 'Operational Interaction')}"
        flow = factory.create_flow_connection_usage(
            name=label,
            owner=root,
            flow_connection_definition=[definitions["OperationalExchange"]],
            source=[before],
            target=[after],
            source_feature=before,
            target_feature=[after],
            related_feature=[before, after],
            is_directed=True,
        )
        _documentation(factory, flow, json.dumps(
            {"scenario_step": pos, **copy.deepcopy(step)},
            ensure_ascii=False, sort_keys=True, default=str
        ))
        expected.append(label)

    for before, after in zip(actions, actions[1:]):
        factory.create_succession(
            owner=root,
            source=[before],
            target=[after],
            source_feature=before,
            target_feature=[after],
            related_feature=[before, after],
            trigger_step=[before],
            effect_step=[after],
        )
    return {
        "sam_id": _element_id(root),
        "final_name": _clean(scenario.get("name") or scenario.get("id") or "Operational Scenario"),
        "expected": expected,
    }


def sync_level1_incremental_with_scenarios(
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
    plan = build_incremental_plan_with_scenarios(model, scenarios=scenarios, settings=settings)
    if expected_digest and expected_digest != plan.get("snapshot_digest"):
        raise SamLevel1SyncError("The model changed after the scenario change set was reviewed.")
    if not plan.get("supported"):
        raise SamLevel1SyncError("; ".join(plan.get("unsupported_changes") or []))

    creates = list(plan.get("scenario_creates") or [])
    updates = list(plan.get("scenario_updates") or [])
    deletes = list(plan.get("scenario_deletes") or [])
    if not (creates or updates or deletes):
        result = sync_level1_incremental_with_communication(
            _shadow(model, state, scenarios),
            scenarios=scenarios,
            settings=settings,
            expected_digest=expected_digest,
            connector_class=connector_class,
            project_manager_class=project_manager_class,
            factory_class=factory_class,
        )
        if isinstance(result.get("sync_state"), dict):
            result["sync_state"]["scenario_tracking_revision"] = SCENARIO_TRACKING_REVISION
            result["sync_state"].setdefault("scenarios", copy.deepcopy(state.get("scenarios") or {}))
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
    staged = []
    write_started = perf_counter()
    project.start_transactional_mode()
    try:
        for item in creates + [x for x in updates if x.get("change_kind") == "replace"]:
            scenario = item.get("scenario") if isinstance(item.get("scenario"), dict) else {}
            stage = _create_tree(
                factory, package, library["definitions"], model, scenario,
                f"__MBSE_SCENARIO_{uuid4().hex[:10]}"
            )
            stage.update({"scenario_id": item.get("scenario_id"), "scenario": scenario})
            if item in updates:
                stage["old_sam_id"] = item.get("sam_id")
            staged.append(stage)

        for item in updates:
            if item.get("change_kind") != "rename":
                continue
            element = project.find_element_by_id(str(item.get("sam_id") or ""))
            if element is None:
                raise SamLevel1SyncError("Scenario rename target disappeared.")
            element.name = item["new_name"]

        for item in deletes:
            element = project.find_element_by_id(str(item.get("sam_id") or ""))
            if element is None:
                raise SamLevel1SyncError("Scenario delete target disappeared.")
            _delete_owned_tree(element, project)

        for stage in staged:
            old_id = stage.get("old_sam_id")
            if old_id:
                old = project.find_element_by_id(str(old_id))
                if old is None:
                    raise SamLevel1SyncError("Scenario replacement target disappeared.")
                _delete_owned_tree(old, project)
            element = project.find_element_by_id(str(stage.get("sam_id") or ""))
            if element is None:
                raise SamLevel1SyncError("Staged scenario disappeared.")
            element.name = stage["final_name"]
        project.stop_transactional_mode()
    except Exception as exc:
        raise SamLevel1SyncError(f"SAM scenario transaction failed: {exc}") from exc
    write_seconds = perf_counter() - write_started

    _, _, verified, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=resolved_factory,
    )
    for stage in staged:
        element = verified.find_element_by_id(str(stage.get("sam_id") or ""))
        if element is None or _element_name(element) != stage["final_name"]:
            raise SamLevel1SyncError("Scenario publication verification failed.")
        names = {_element_name(x) for x in _descendants(verified, element)}
        if any(name not in names for name in stage["expected"]):
            raise SamLevel1SyncError("Scenario path verification failed after SAM reload.")

    current = _by_id(scenarios)
    records = copy.deepcopy(state.get("scenarios") or {})
    for item in deletes:
        records.pop(str(item.get("scenario_id") or ""), None)
    staged_by_id = {str(x.get("scenario_id") or ""): x for x in staged}
    for item in updates:
        key = str(item.get("scenario_id") or "")
        sam_id = item.get("sam_id") if item.get("change_kind") == "rename" else staged_by_id[key]["sam_id"]
        records[key] = _record(current[key], str(sam_id or ""))
    for item in creates:
        key = str(item.get("scenario_id") or "")
        records[key] = _record(current[key], str(staged_by_id[key]["sam_id"] or ""))

    new_state = copy.deepcopy(state)
    new_state["scenarios"] = records
    new_state["scenario_tracking_revision"] = SCENARIO_TRACKING_REVISION
    new_state["scenarios_fingerprint"] = _scenario_fingerprint(_valid(scenarios))
    new_state["snapshot_digest"] = level1_snapshot_digest(model, scenarios)
    return {
        **plan,
        "status": "synced",
        "mode": "incremental_scenario_change_set",
        "sam_write_performed": True,
        "sync_state": new_state,
        "scenario_delta": dict(plan.get("scenario_counts") or {}),
        "timings": {
            "write_seconds": round(write_seconds, 3),
            "total_seconds": round(perf_counter() - started, 3),
        },
    }
