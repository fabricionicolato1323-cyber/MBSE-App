"""Reliable direct-create writer for SAM Level 1B snapshots.

PySAM 0.3.1 documents Factory direct creation for new elements. Its transactional
creation path has known scripting-element inconsistencies and, against a live SAM
server, can accept the aggregate commit without leaving the created package behind.
This writer therefore uses the documented direct-create path and only publishes the
final package name after all content has been created.
"""

from __future__ import annotations

from typing import Any

from sam_connection import SamSettings
from sam_level1_sync import (
    SamLevel1SyncError,
    _create_library_definitions,
    _create_relationships,
    _create_scenarios,
    _create_source_nodes,
    _documentation,
    _load_pysam_classes,
    _rows,
    build_level1_sync_plan,
)
from sysml_v2 import generate_sysml_v2


def level1_completion_marker_name(snapshot_digest: str) -> str:
    """Return the server-visible marker proving a Level 1 snapshot finished."""
    digest = str(snapshot_digest or "").strip()
    return f"MBSE_Level1_Complete_{digest[:8] or 'unknown'}"


def level1_staging_package_name(package_name: str) -> str:
    """Return a name that can never be mistaken for a completed snapshot."""
    return f"{package_name}__INCOMPLETE"


def _element_id(element: Any) -> str | None:
    for attr in ("id", "_id"):
        value = getattr(element, attr, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _matches(project: Any, name: str) -> list[Any]:
    return list(project.find_elements_by_name(name) or [])


def _rename_scripting_element(element: Any, name: str) -> None:
    """Rename both real PySAM scripting elements and lightweight test doubles."""
    if hasattr(element, "_name"):
        element._name = name
    else:
        element.name = name


def _ensure_no_incomplete_snapshot(
    project: Any,
    *,
    package_name: str,
    staging_name: str,
    marker_name: str,
) -> dict[str, Any] | None:
    completed = _matches(project, package_name)
    markers = _matches(project, marker_name)
    if completed and markers:
        return {
            "status": "already_synced",
            "sam_write_performed": False,
            "sam_package_id": _element_id(completed[0]),
            "completion_marker_name": marker_name,
        }
    if completed:
        raise SamLevel1SyncError(
            f"SAM contains a Level 1 package named {package_name!r}, but its completion "
            "marker is missing. Treat it as an incomplete previous transfer; remove that "
            "package in SAM before retrying."
        )
    if _matches(project, staging_name):
        raise SamLevel1SyncError(
            f"SAM contains an incomplete Level 1 staging package named {staging_name!r}. "
            "Remove that staging package in SAM before retrying so no partial model is "
            "mistaken for a new transfer."
        )
    return None


def sync_level1_to_sam_direct(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None,
    settings: SamSettings,
    expected_digest: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Create one immutable Level 1 snapshot through PySAM direct-create calls.

    The package is initially named ``__INCOMPLETE``. Only after every semantic
    element, relationship, scenario and textual representation has been accepted
    is a completion marker created and the package renamed to its final Level 1
    name. A separate fresh-project verification is performed by the caller.
    """
    model = payload if isinstance(payload, dict) else {}
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    plan = build_level1_sync_plan(
        model,
        scenarios=scenario_rows,
        project_id=settings.project_id,
    )
    plan["mode"] = "verified_direct_create_snapshot"

    if plan["status"] != "ready":
        raise SamLevel1SyncError(
            "Level 1 transfer is blocked because the snapshot contains unsupported or missing semantic content."
        )
    if expected_digest and expected_digest != plan["snapshot_digest"]:
        raise SamLevel1SyncError(
            "The model changed after the transfer plan was prepared. Review the new plan before sending."
        )

    if connector_class is None or project_manager_class is None or factory_class is None:
        default_connector, default_manager, default_factory = _load_pysam_classes()
        connector_class = connector_class or default_connector
        project_manager_class = project_manager_class or default_manager
        factory_class = factory_class or default_factory

    connector = connector_class(
        server_url=settings.server_url,
        organization_id=settings.organization_id,
        token=settings.access_token,
        use_ssl=settings.use_ssl,
    )
    manager = project_manager_class(connector=connector)
    project = manager.get_scripting_project(settings.project_id)
    if project is None:
        raise SamLevel1SyncError("The configured SAM project could not be loaded.")

    package_name = str(plan["package_name"])
    marker_name = level1_completion_marker_name(plan["snapshot_digest"])
    staging_name = level1_staging_package_name(package_name)
    existing = _ensure_no_incomplete_snapshot(
        project,
        package_name=package_name,
        staging_name=staging_name,
        marker_name=marker_name,
    )
    if existing is not None:
        return {**plan, **existing}

    root = project.get_root_package()
    factory = factory_class(project, connector)
    model_package = None
    stage = "creating the Level 1 staging package"
    try:
        model_package = factory.create_package(name=staging_name, owner=root)
        if not _matches(project, staging_name):
            raise SamLevel1SyncError(
                "PySAM returned from create_package(), but the staging package is not visible "
                "in the reloaded project. No Level 1 content will be sent."
            )

        stage = "creating Level 1 package metadata"
        _documentation(
            factory,
            model_package,
            "MBSE-App Level 1B immutable snapshot.\n"
            f"Model: {plan['model_name']}\n"
            f"Snapshot SHA-256: {plan['snapshot_digest']}\n"
            f"Source elements: {plan['counts']['elements']}\n"
            f"Source relationships: {plan['counts']['relationships']}\n"
            f"Operational scenarios: {plan['counts']['scenarios']}",
        )

        stage = "creating the ArcadiaOA SysML v2 definitions"
        definitions = _create_library_definitions(factory, model_package)
        nodes = _rows(model.get("nodes"))
        edges = _rows(model.get("edges"))
        source_node_by_id = {str(node.get("id")): node for node in nodes}

        stage = "creating Operational Analysis elements"
        elements, structure, behavior, characteristic_count = _create_source_nodes(
            factory,
            nodes=nodes,
            edges=edges,
            definitions=definitions,
            model_package=model_package,
        )

        stage = "creating Operational Analysis relationships"
        relationship_count = _create_relationships(
            factory,
            edges=edges,
            elements=elements,
            definitions=definitions,
            model_package=model_package,
            structure=structure,
            behavior=behavior,
        )

        stage = "creating Operational Scenarios"
        scenario_count, scenario_step_count = _create_scenarios(
            factory,
            scenarios=scenario_rows,
            source_nodes=source_node_by_id,
            definitions=definitions,
            model_package=model_package,
        )

        stage = "creating the Level 1 textual SysML v2 representation"
        sysml_text = generate_sysml_v2(model, scenarios=scenario_rows, drafts=[])
        factory.create_textual_representation(
            owner=model_package,
            represented_element=model_package,
            language="SysML v2",
            body=sysml_text,
        )

        stage = "creating the Level 1 completion marker"
        factory.create_package(name=marker_name, owner=model_package)
        if not _matches(project, marker_name):
            raise SamLevel1SyncError(
                "The Level 1 completion marker was not visible after its direct create call."
            )

        stage = "publishing the completed Level 1 package"
        _rename_scripting_element(model_package, package_name)
        completed_matches = _matches(project, package_name)
        if not completed_matches:
            raise SamLevel1SyncError(
                "All Level 1 content was created, but the staging package could not be renamed "
                "to its final package name."
            )
    except SamLevel1SyncError:
        raise
    except Exception as exc:
        suffix = (
            f" A partial staging package named {staging_name!r} may remain in SAM; "
            "it is deliberately not considered synchronized."
            if model_package is not None
            else ""
        )
        raise SamLevel1SyncError(
            f"SAM Level 1 direct creation failed while {stage}: {exc}.{suffix}"
        ) from exc

    return {
        **plan,
        "status": "synced",
        "sam_write_performed": True,
        "sam_package_id": _element_id(completed_matches[0]),
        "completion_marker_name": marker_name,
        "staging_package_name": staging_name,
        "created": {
            "source_elements": len(elements),
            "native_relationships": relationship_count,
            "characteristic_attributes": characteristic_count,
            "scenarios": scenario_count,
            "scenario_steps": scenario_step_count,
            "textual_level1_representation": 1,
            "completion_marker": 1,
        },
    }
