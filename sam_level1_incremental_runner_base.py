"""Persistent dispatcher for explicit Level 1 incremental SAM synchronization.

The manifest is local runtime state, not part of the ArcadiaOA library and not a
visible SAM model element. It records the last verified mapping between stable
MBSE-App IDs/relationship identities and SAM IDs for one project/model pair.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from sam_connection import SamSettings
from sam_level1_incremental import (
    LEGACY_SYNC_STATE_VERSION,
    _adopt_supported_relationship_elements,
    _build_state,
    _nodes_by_id,
    _unique_descendant_by_name,
    build_incremental_plan,
    migrate_legacy_relationship_state,
    sync_level1_incremental,
)
from sam_level1_managed_direct import sync_level1_to_sam_managed_direct
from sam_level1_sync import _model_name, _rows, _slug, build_level1_sync_plan
from sam_level1_transactional import (
    ARCADIA_OA_LIBRARY_PACKAGE,
    _element_id,
    _element_name,
    _load_project,
    level1_instance_package_name,
)

_RUNTIME_ROOT = Path(__file__).resolve().parent / ".web_runtime" / "sam_sync"


def _manifest_path(model: dict[str, Any], settings: SamSettings) -> Path:
    project_key = hashlib.sha256(settings.project_id.encode("utf-8")).hexdigest()[:16]
    model_key = _slug(_model_name(model), fallback="Operational_Analysis")
    return _RUNTIME_ROOT / project_key / f"{model_key}.json"


def _load_manifest(model: dict[str, Any], settings: SamSettings) -> dict[str, Any] | None:
    path = _manifest_path(model, settings)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("project_id") != settings.project_id:
        return None
    return value


def _save_manifest(model: dict[str, Any], settings: SamSettings, state: dict[str, Any]) -> None:
    path = _manifest_path(model, settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _with_manifest(model: dict[str, Any], state: dict[str, Any] | None) -> dict[str, Any]:
    value = copy.deepcopy(model)
    graph = value.get("graph") if isinstance(value.get("graph"), dict) else {}
    graph = dict(graph)
    if state is not None:
        graph["sam_sync"] = state
    value["graph"] = graph
    return value


def _manifest_version(manifest: dict[str, Any] | None) -> int:
    if not isinstance(manifest, dict):
        return 0
    try:
        return int(manifest.get("version", 0))
    except (TypeError, ValueError):
        return 0


def _prepare_manifest_for_relationship_plan(
    model: dict[str, Any],
    scenarios: list[dict[str, Any]],
    manifest: dict[str, Any],
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Migrate a v1 manifest in memory only when a relationship delta requires it."""
    if _manifest_version(manifest) != LEGACY_SYNC_STATE_VERSION:
        return manifest
    # Always reconstruct relationship identity for a legacy manifest read-only.
    # Even a node-only change must not silently promote v1 to v2 without mapping
    # the relationships that already exist in the managed SAM instance.
    return migrate_legacy_relationship_state(
        model,
        scenarios=scenarios,
        state=manifest,
        settings=settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )


def preview_level1_with_incremental_state(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None,
    settings: SamSettings,
) -> dict[str, Any]:
    """Build the user-reviewable SAM change set without performing a SAM write."""
    model = payload if isinstance(payload, dict) else {}
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    full = build_level1_sync_plan(
        model,
        scenarios=scenario_rows,
        project_id=settings.project_id,
    )
    if full.get("status") != "ready":
        return {
            **full,
            "sync_status": "blocked",
            "delta": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
            "relationship_delta": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
            "library": {"action": "not_evaluated", "package_name": ARCADIA_OA_LIBRARY_PACKAGE},
            "instance": {"action": "not_evaluated"},
            "unsupported_changes": ["Level 1 semantic validation is blocked."],
        }

    manifest = _load_manifest(model, settings)
    if manifest is None:
        counts = full.get("counts") if isinstance(full.get("counts"), dict) else {}
        return {
            **full,
            "mode": "manual_baseline_sync",
            "sync_status": "never_synchronized",
            "supported": True,
            "delta": {
                "create": int(counts.get("elements") or 0),
                "update": 0,
                "delete": 0,
                "unchanged": 0,
            },
            "relationship_delta": {
                "create": int(counts.get("relationships") or 0),
                "update": 0,
                "delete": 0,
                "unchanged": 0,
            },
            "relationship_creates": [],
            "relationship_updates": [],
            "relationship_deletes": [],
            "scenario_delta": {
                "create": int(counts.get("scenarios") or 0),
                "update": 0,
                "delete": 0,
            },
            "library": {
                "action": "create_or_reuse",
                "package_name": ARCADIA_OA_LIBRARY_PACKAGE,
            },
            "instance": {
                "action": "create_or_adopt",
                "package_name": level1_instance_package_name(
                    full["model_name"], full["snapshot_digest"]
                ),
            },
            "unsupported_changes": [],
        }

    # The migration is read-only and intentionally is NOT saved during preview.
    # The local manifest is updated only after a confirmed + verified sync.
    manifest_for_plan = _prepare_manifest_for_relationship_plan(
        model,
        scenario_rows,
        manifest,
        settings,
    )
    working_model = _with_manifest(model, manifest_for_plan)
    incremental = build_incremental_plan(
        working_model,
        scenarios=scenario_rows,
        settings=settings,
    )
    sync_status = (
        "up_to_date"
        if incremental.get("mode") == "incremental_noop"
        else "local_changes"
    )
    supported = bool(incremental.get("supported"))
    if not supported:
        sync_status = "local_changes_blocked"

    relationship_counts = dict(incremental.get("relationship_counts") or {})
    return {
        **full,
        "mode": incremental.get("mode"),
        "status": "ready" if supported else "blocked",
        "supported": supported,
        "sync_status": sync_status,
        "delta": dict(incremental.get("counts") or {}),
        "creates": list(incremental.get("creates") or []),
        "updates": list(incremental.get("updates") or []),
        "deletes": list(incremental.get("deletes") or []),
        "relationship_delta": {
            **relationship_counts,
            "pending": bool(incremental.get("relationship_changes_pending")),
        },
        "relationship_creates": list(incremental.get("relationship_creates") or []),
        "relationship_updates": list(incremental.get("relationship_updates") or []),
        "relationship_deletes": list(incremental.get("relationship_deletes") or []),
        "scenario_delta": {
            "pending": bool(incremental.get("scenario_changes_pending")),
        },
        "library": {
            "action": "reuse",
            "package_name": manifest_for_plan.get("library_package_name") or ARCADIA_OA_LIBRARY_PACKAGE,
        },
        "instance": {
            "action": "reuse",
            "package_name": manifest_for_plan.get("instance_package_name"),
            "package_id": manifest_for_plan.get("instance_package_id"),
        },
        "package_name": manifest_for_plan.get("instance_package_name"),
        "manifest_migrated_readonly": manifest_for_plan is not manifest,
        "unsupported_changes": list(incremental.get("unsupported_changes") or []),
    }


def _adopt_current_managed_instance(
    model: dict[str, Any],
    scenarios: list[dict[str, Any]],
    settings: SamSettings,
    *,
    connector_class: type[Any] | None,
    project_manager_class: type[Any] | None,
    factory_class: type[Any] | None,
) -> dict[str, Any] | None:
    """Adopt the current MBSE_Instance package, never a legacy MBSE_Level1 package."""
    plan = build_level1_sync_plan(model, scenarios=scenarios, project_id=settings.project_id)
    managed_name = level1_instance_package_name(plan["model_name"], plan["snapshot_digest"])
    _, _, project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    matches = list(project.find_elements_by_name(managed_name) or [])
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


def sync_level1_with_incremental_state(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None,
    settings: SamSettings,
    expected_digest: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Create/adopt a baseline once, then synchronize only the reviewed delta."""
    model = payload if isinstance(payload, dict) else {}
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    manifest = _load_manifest(model, settings)

    if manifest is None:
        adopted = _adopt_current_managed_instance(
            model,
            scenario_rows,
            settings,
            connector_class=connector_class,
            project_manager_class=project_manager_class,
            factory_class=factory_class,
        )
        if adopted is None:
            baseline = sync_level1_to_sam_managed_direct(
                model,
                scenarios=scenario_rows,
                settings=settings,
                expected_digest=expected_digest,
                connector_class=connector_class,
                project_manager_class=project_manager_class,
                factory_class=factory_class,
            )
            adopted = _adopt_current_managed_instance(
                model,
                scenario_rows,
                settings,
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
            baseline["delta"] = {
                "create": len(_nodes_by_id(model)),
                "update": 0,
                "delete": 0,
                "unchanged": 0,
            }
            baseline["relationship_delta"] = {
                "create": len(_rows(model.get("edges"))),
                "update": 0,
                "delete": 0,
                "unchanged": 0,
            }
            return baseline

        _save_manifest(model, settings, adopted)
        manifest = adopted

    manifest = _prepare_manifest_for_relationship_plan(
        model,
        scenario_rows,
        manifest,
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    working_model = _with_manifest(model, manifest)
    result = sync_level1_incremental(
        working_model,
        scenarios=scenario_rows,
        settings=settings,
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
