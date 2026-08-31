"""Persistent dispatcher for reviewed Level 1 incremental SAM synchronization.

Level 1C support for nodes, Operational Exchanges and Communication Means is
extended here with Level 1D Operational Scenario tracking and synchronization.
"""
from __future__ import annotations

from typing import Any

import sam_level1_incremental_runner_base as _base
from sam_connection import SamSettings
from sam_level1_communication_incremental import enrich_state_with_current_communication_means
from sam_level1_managed_direct import sync_level1_to_sam_managed_direct
from sam_level1_scenario_incremental import (
    build_incremental_plan_with_scenarios,
    enrich_state_with_current_scenarios,
    sync_level1_incremental_with_scenarios,
)
from sam_level1_sync import _rows, build_level1_sync_plan
from sam_level1_transactional import ARCADIA_OA_LIBRARY_PACKAGE, level1_instance_package_name

_RUNTIME_ROOT = _base._RUNTIME_ROOT
_manifest_path = _base._manifest_path
_load_manifest = _base._load_manifest
_save_manifest = _base._save_manifest
_with_manifest = _base._with_manifest
_manifest_version = _base._manifest_version


def _prepare_manifest_for_relationship_plan(
    model: dict[str, Any], scenarios: list[dict[str, Any]], manifest: dict[str, Any],
    settings: SamSettings, *, connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None, factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    prepared = _base._prepare_manifest_for_relationship_plan(
        model, scenarios, manifest, settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    prepared = enrich_state_with_current_communication_means(
        model, scenarios=scenarios, state=prepared, settings=settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class, require_migration_proof=True,
    )
    return enrich_state_with_current_scenarios(
        model, scenarios=scenarios, state=prepared, settings=settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class, require_migration_proof=True,
    )


def _adopt_current_managed_instance(
    model: dict[str, Any], scenarios: list[dict[str, Any]], settings: SamSettings,
    *, connector_class: type[Any] | None, project_manager_class: type[Any] | None,
    factory_class: type[Any] | None,
) -> dict[str, Any] | None:
    adopted = _base._adopt_current_managed_instance(
        model, scenarios, settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    if adopted is None:
        return None
    adopted = enrich_state_with_current_communication_means(
        model, scenarios=scenarios, state=adopted, settings=settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class, require_migration_proof=False,
    )
    return enrich_state_with_current_scenarios(
        model, scenarios=scenarios, state=adopted, settings=settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class, require_migration_proof=False,
    )


def preview_level1_with_incremental_state(
    payload: Any, *, scenarios: list[dict[str, Any]] | None, settings: SamSettings,
) -> dict[str, Any]:
    model = payload if isinstance(payload, dict) else {}
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    full = build_level1_sync_plan(model, scenarios=scenario_rows, project_id=settings.project_id)
    if full.get("status") != "ready":
        return {
            **full, "sync_status": "blocked",
            "delta": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
            "relationship_delta": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
            "scenario_delta": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
            "library": {"action": "not_evaluated", "package_name": ARCADIA_OA_LIBRARY_PACKAGE},
            "instance": {"action": "not_evaluated"},
            "unsupported_changes": ["Level 1 semantic validation is blocked."],
        }

    manifest = _load_manifest(model, settings)
    if manifest is None:
        counts = full.get("counts") if isinstance(full.get("counts"), dict) else {}
        return {
            **full, "mode": "manual_baseline_sync", "sync_status": "never_synchronized",
            "supported": True,
            "delta": {"create": int(counts.get("elements") or 0), "update": 0, "delete": 0, "unchanged": 0},
            "relationship_delta": {"create": int(counts.get("relationships") or 0), "update": 0, "delete": 0, "unchanged": 0},
            "relationship_creates": [], "relationship_updates": [], "relationship_deletes": [],
            "scenario_delta": {"create": int(counts.get("scenarios") or 0), "update": 0, "delete": 0, "unchanged": 0},
            "scenario_creates": [], "scenario_updates": [], "scenario_deletes": [],
            "library": {"action": "create_or_reuse", "package_name": ARCADIA_OA_LIBRARY_PACKAGE},
            "instance": {"action": "create_or_adopt", "package_name": level1_instance_package_name(full["model_name"], full["snapshot_digest"])},
            "unsupported_changes": [],
        }

    prepared = _prepare_manifest_for_relationship_plan(model, scenario_rows, manifest, settings)
    incremental = build_incremental_plan_with_scenarios(
        _with_manifest(model, prepared), scenarios=scenario_rows, settings=settings
    )
    supported = bool(incremental.get("supported"))
    sync_status = "up_to_date" if incremental.get("mode") == "incremental_noop" else "local_changes"
    if not supported:
        sync_status = "local_changes_blocked"
    relationships = dict(incremental.get("relationship_counts") or {})
    scenario_counts = dict(incremental.get("scenario_counts") or {})
    return {
        **full, "mode": incremental.get("mode"), "status": "ready" if supported else "blocked",
        "supported": supported, "sync_status": sync_status,
        "delta": dict(incremental.get("counts") or {}),
        "creates": list(incremental.get("creates") or []),
        "updates": list(incremental.get("updates") or []),
        "deletes": list(incremental.get("deletes") or []),
        "relationship_delta": {**relationships, "pending": bool(incremental.get("relationship_changes_pending"))},
        "relationship_creates": list(incremental.get("relationship_creates") or []),
        "relationship_updates": list(incremental.get("relationship_updates") or []),
        "relationship_deletes": list(incremental.get("relationship_deletes") or []),
        "scenario_delta": {**scenario_counts, "pending": bool(incremental.get("scenario_changes_pending"))},
        "scenario_creates": list(incremental.get("scenario_creates") or []),
        "scenario_updates": list(incremental.get("scenario_updates") or []),
        "scenario_deletes": list(incremental.get("scenario_deletes") or []),
        "library": {"action": "reuse", "package_name": prepared.get("library_package_name") or ARCADIA_OA_LIBRARY_PACKAGE},
        "instance": {"action": "reuse", "package_name": prepared.get("instance_package_name"), "package_id": prepared.get("instance_package_id")},
        "package_name": prepared.get("instance_package_name"),
        "manifest_migrated_readonly": prepared is not manifest,
        "unsupported_changes": list(incremental.get("unsupported_changes") or []),
    }


def sync_level1_with_incremental_state(
    payload: Any, *, scenarios: list[dict[str, Any]] | None, settings: SamSettings,
    expected_digest: str | None = None, connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None, factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    model = payload if isinstance(payload, dict) else {}
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    manifest = _load_manifest(model, settings)
    if manifest is None:
        adopted = _adopt_current_managed_instance(
            model, scenario_rows, settings,
            connector_class=connector_class,
            project_manager_class=project_manager_class,
            factory_class=factory_class,
        )
        if adopted is None:
            baseline = sync_level1_to_sam_managed_direct(
                model, scenarios=scenario_rows, settings=settings,
                expected_digest=expected_digest,
                connector_class=connector_class,
                project_manager_class=project_manager_class,
                factory_class=factory_class,
            )
            adopted = _adopt_current_managed_instance(
                model, scenario_rows, settings,
                connector_class=connector_class,
                project_manager_class=project_manager_class,
                factory_class=factory_class,
            )
            if adopted is None:
                baseline["incremental_baseline_ready"] = False
                return baseline
            _save_manifest(model, settings, adopted)
            baseline["sync_state"] = adopted
            baseline["incremental_baseline_ready"] = True
            baseline["mode"] = "baseline_created_or_adopted_for_incremental_sync"
            baseline["delta"] = {"create": len(_base._nodes_by_id(model)), "update": 0, "delete": 0, "unchanged": 0}
            baseline["relationship_delta"] = {"create": len(_rows(model.get("edges"))), "update": 0, "delete": 0, "unchanged": 0}
            baseline["scenario_delta"] = {"create": len([x for x in scenario_rows if x.get("valid") is not False]), "update": 0, "delete": 0, "unchanged": 0}
            return baseline
        _save_manifest(model, settings, adopted)
        manifest = adopted

    prepared = _prepare_manifest_for_relationship_plan(
        model, scenario_rows, manifest, settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    result = sync_level1_incremental_with_scenarios(
        _with_manifest(model, prepared), scenarios=scenario_rows, settings=settings,
        expected_digest=expected_digest,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    state = result.get("sync_state")
    if isinstance(state, dict):
        _save_manifest(model, settings, state)
    result["incremental_baseline_ready"] = isinstance(state, dict)
    return result
