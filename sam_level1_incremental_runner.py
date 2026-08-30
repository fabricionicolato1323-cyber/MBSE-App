"""Persistent dispatcher for Level 1 incremental SAM synchronization.

The manifest is local runtime state, not part of the ArcadiaOA library and not a
visible SAM model element. It records only the last verified mapping between
stable MBSE-App IDs and SAM IDs for one project/model pair.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from sam_connection import SamSettings
from sam_level1_incremental import (
    _build_state,
    _nodes_by_id,
    _unique_descendant_by_name,
    sync_level1_incremental,
)
from sam_level1_managed_direct import sync_level1_to_sam_managed_direct
from sam_level1_sync import _model_name, _rows, _slug, build_level1_sync_plan
from sam_level1_transactional import (
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
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _with_manifest(model: dict[str, Any], state: dict[str, Any] | None) -> dict[str, Any]:
    value = copy.deepcopy(model)
    graph = value.get("graph") if isinstance(value.get("graph"), dict) else {}
    graph = dict(graph)
    if state is not None:
        graph["sam_sync"] = state
    value["graph"] = graph
    return value


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
    return _build_state(
        model,
        scenarios,
        settings=settings,
        package_name=_element_name(package),
        package_id=_element_id(package),
        node_elements=node_elements,
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
    """Adopt/create a baseline once, then synchronize supported deltas only."""
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
            # No current managed instance exists yet. Create/reuse the managed
            # baseline once, then adopt exactly that MBSE_Instance package.
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
            return baseline

        _save_manifest(model, settings, adopted)
        manifest = adopted

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
