"""Managed direct SAM Level 1 transport with one reusable ArcadiaOA library.

The live SAM used for Gate 1B accepts PySAM direct creates reliably, while
transactional creation of brand-new elements can return success without
materializing those elements at the branch head. This module therefore uses the
verified direct-create path, but keeps the model clean by separating:

* one reusable ``MBSE_ArcadiaOA_Library_v1`` LibraryPackage; and
* one ``MBSE_Instance_<model>_<digest>`` package per immutable model snapshot.

Both artifacts are created under a unique ``__INCOMPLETE_<id>`` staging name and
are renamed to their final name only after all required content has been accepted.
The final name itself is therefore the completion proof; no extra visible marker
Package is needed.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import uuid4

from sam_connection import SamSettings
from sam_level1_direct import _MetadataTolerantFactory, _rename_scripting_element
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
from sam_level1_transactional import (
    ARCADIA_OA_LIBRARY_PACKAGE,
    ARCADIA_OA_NAMESPACE,
    _REQUIRED_DEFINITIONS,
    _descendant_named,
    _element_id,
    _load_project,
    _unique_match,
    level1_instance_package_name,
)
from sam_reload_safe_factory import ReloadSafeFactory


def _matches(project: Any, name: str) -> list[Any]:
    return list(project.find_elements_by_name(name) or [])


def _unique_staging_name(project: Any, final_name: str) -> str:
    for _ in range(20):
        candidate = f"{final_name}__INCOMPLETE_{uuid4().hex[:8]}"
        if not _matches(project, candidate):
            return candidate
    raise SamLevel1SyncError(
        f"Could not allocate a unique staging name for {final_name!r}."
    )


def _library_status(project: Any) -> dict[str, Any]:
    package = _unique_match(project, ARCADIA_OA_LIBRARY_PACKAGE)
    namespace = None
    definitions: dict[str, Any] = {}
    if package is not None:
        namespace = _descendant_named(project, package, ARCADIA_OA_NAMESPACE)
        if namespace is not None:
            for name in _REQUIRED_DEFINITIONS:
                definitions[name] = _descendant_named(project, namespace, name)
    missing = [name for name in _REQUIRED_DEFINITIONS if definitions.get(name) is None]
    return {
        "loaded": package is not None and namespace is not None and not missing,
        "package": package,
        "package_id": _element_id(package) if package is not None else None,
        "namespace": namespace,
        "namespace_id": _element_id(namespace) if namespace is not None else None,
        "definitions": definitions,
        "missing_definitions": missing,
    }


def _fresh_project(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None,
    project_manager_class: type[Any] | None,
    factory_class: type[Any] | None,
) -> tuple[Any, Any, Any, type[Any]]:
    return _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )


def ensure_arcadia_oa_library_direct(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Create the managed ArcadiaOA library once using verified direct creates."""
    total_started = perf_counter()
    connect_started = perf_counter()
    connector, _, project, resolved_factory = _fresh_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    connection_seconds = perf_counter() - connect_started

    current = _library_status(project)
    if current["loaded"]:
        return {
            "status": "already_loaded",
            "loaded": True,
            "sam_write_performed": False,
            "package_name": ARCADIA_OA_LIBRARY_PACKAGE,
            "package_id": current["package_id"],
            "missing_definitions": [],
            "timings": {
                "connection_seconds": round(connection_seconds, 3),
                "write_seconds": 0.0,
                "verification_seconds": 0.0,
                "total_seconds": round(perf_counter() - total_started, 3),
            },
        }
    if current["package"] is not None:
        raise SamLevel1SyncError(
            "The final managed ArcadiaOA library package exists but is incomplete. "
            "MBSE-App will not create a second final library with the same name."
        )

    root = project.get_root_package()
    staging_name = _unique_staging_name(project, ARCADIA_OA_LIBRARY_PACKAGE)
    raw_factory = resolved_factory(project, connector)
    factory = _MetadataTolerantFactory(ReloadSafeFactory(project, raw_factory))
    library_package = None
    write_started = perf_counter()
    stage = "creating the managed ArcadiaOA library package"
    try:
        library_package = factory.create_library_package(name=staging_name, owner=root)
        stage = "creating the ArcadiaOA reusable definitions"
        _create_library_definitions(factory, library_package)
        stage = "publishing the managed ArcadiaOA library"
        _rename_scripting_element(project, library_package, ARCADIA_OA_LIBRARY_PACKAGE)
    except Exception as exc:
        suffix = (
            f" A staging library named {staging_name!r} may remain in SAM and is not "
            "considered a valid managed library."
            if library_package is not None
            else ""
        )
        raise SamLevel1SyncError(
            f"SAM managed library direct creation failed while {stage}: {exc}.{suffix}"
        ) from exc
    write_seconds = perf_counter() - write_started

    verify_started = perf_counter()
    _, _, verified_project, _ = _fresh_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=resolved_factory,
    )
    verified = _library_status(verified_project)
    verification_seconds = perf_counter() - verify_started
    if not verified["loaded"]:
        raise SamLevel1SyncError(
            "The ArcadiaOA library was published, but a fresh SAM read did not find all "
            "required definitions. Missing: "
            + ", ".join(verified["missing_definitions"])
        )

    return {
        "status": "loaded",
        "loaded": True,
        "sam_write_performed": True,
        "package_name": ARCADIA_OA_LIBRARY_PACKAGE,
        "package_id": verified["package_id"],
        "missing_definitions": [],
        "metadata_warnings": list(factory.warnings),
        "timings": {
            "connection_seconds": round(connection_seconds, 3),
            "write_seconds": round(write_seconds, 3),
            "verification_seconds": round(verification_seconds, 3),
            "total_seconds": round(perf_counter() - total_started, 3),
        },
    }


def sync_level1_to_sam_managed_direct(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None,
    settings: SamSettings,
    expected_digest: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Reuse one ArcadiaOA library and publish only the concrete model instance."""
    total_started = perf_counter()
    model = payload if isinstance(payload, dict) else {}
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    plan = build_level1_sync_plan(
        model,
        scenarios=scenario_rows,
        project_id=settings.project_id,
    )
    if plan["status"] != "ready":
        raise SamLevel1SyncError(
            "Level 1 transfer is blocked because the snapshot contains unsupported or "
            "missing semantic content."
        )
    if expected_digest and expected_digest != plan["snapshot_digest"]:
        raise SamLevel1SyncError(
            "The model changed after the transfer plan was prepared. Review the new plan "
            "before sending."
        )

    library = ensure_arcadia_oa_library_direct(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )

    connect_started = perf_counter()
    connector, _, project, resolved_factory = _fresh_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    connection_seconds = perf_counter() - connect_started
    library_state = _library_status(project)
    if not library_state["loaded"]:
        raise SamLevel1SyncError(
            "The reusable ArcadiaOA library could not be resolved before model instantiation."
        )
    definitions = library_state["definitions"]

    package_name = level1_instance_package_name(plan["model_name"], plan["snapshot_digest"])
    existing = _matches(project, package_name)
    if len(existing) > 1:
        raise SamLevel1SyncError(
            f"SAM contains more than one managed instance named {package_name!r}."
        )
    if existing:
        return {
            **plan,
            "mode": "managed_direct_library_then_instantiation",
            "package_name": package_name,
            "status": "already_synced",
            "sam_write_performed": False,
            "sam_package_id": _element_id(existing[0]),
            "completion_marker_required": False,
            "completion_marker_name": None,
            "library": {
                "status": library["status"],
                "loaded": True,
                "package_name": ARCADIA_OA_LIBRARY_PACKAGE,
                "package_id": library_state["package_id"],
            },
            "timings": {
                "library_seconds": round(float(library.get("timings", {}).get("total_seconds", 0.0)), 3),
                "connection_seconds": round(connection_seconds, 3),
                "write_seconds": 0.0,
                "verification_seconds": 0.0,
                "total_seconds": round(perf_counter() - total_started, 3),
            },
        }

    staging_name = _unique_staging_name(project, package_name)
    root = project.get_root_package()
    raw_factory = resolved_factory(project, connector)
    factory = _MetadataTolerantFactory(ReloadSafeFactory(project, raw_factory))
    nodes = _rows(model.get("nodes"))
    edges = _rows(model.get("edges"))
    source_node_by_id = {str(node.get("id")): node for node in nodes}
    model_package = None
    stage = "creating the Level 1 instance package"
    write_started = perf_counter()
    try:
        model_package = factory.create_package(name=staging_name, owner=root)
        stage = "creating optional Level 1 instance metadata"
        _documentation(
            factory,
            model_package,
            "MBSE-App Level 1 model instantiation.\n"
            f"Model: {plan['model_name']}\n"
            f"Snapshot SHA-256: {plan['snapshot_digest']}\n"
            f"Shared library: {ARCADIA_OA_LIBRARY_PACKAGE}",
        )
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
        stage = "publishing the completed Level 1 instance"
        _rename_scripting_element(project, model_package, package_name)
    except Exception as exc:
        suffix = (
            f" A staging instance named {staging_name!r} may remain in SAM and is not "
            "considered synchronized."
            if model_package is not None
            else ""
        )
        raise SamLevel1SyncError(
            f"SAM managed Level 1 direct creation failed while {stage}: {exc}.{suffix}"
        ) from exc
    write_seconds = perf_counter() - write_started

    verify_started = perf_counter()
    _, _, verified_project, _ = _fresh_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=resolved_factory,
    )
    verified_matches = _matches(verified_project, package_name)
    verification_seconds = perf_counter() - verify_started
    if len(verified_matches) != 1:
        raise SamLevel1SyncError(
            "The Level 1 instance was published, but a fresh SAM read did not find exactly "
            "one final managed instance."
        )

    return {
        **plan,
        "mode": "managed_direct_library_then_instantiation",
        "package_name": package_name,
        "status": "synced",
        "sam_write_performed": True,
        "sam_package_id": _element_id(verified_matches[0]),
        "completion_marker_required": False,
        "completion_marker_name": None,
        "library": {
            "status": library["status"],
            "loaded": True,
            "package_name": ARCADIA_OA_LIBRARY_PACKAGE,
            "package_id": library_state["package_id"],
        },
        "created": {
            "source_elements": len(elements),
            "native_relationships": relationship_count,
            "characteristic_attributes": characteristic_count,
            "scenarios": scenario_count,
            "scenario_steps": scenario_step_count,
            "textual_level1_representation": 0,
            "visible_completion_marker": 0,
        },
        "metadata_warnings": list(factory.warnings),
        "timings": {
            "library_seconds": round(float(library.get("timings", {}).get("total_seconds", 0.0)), 3),
            "connection_seconds": round(connection_seconds, 3),
            "write_seconds": round(write_seconds, 3),
            "verification_seconds": round(verification_seconds, 3),
            "total_seconds": round(perf_counter() - total_started, 3),
        },
    }
