"""Managed direct transport for the SAM-compatible full OA projection.

This is the live baseline publisher used by the web flow. It keeps the proven
reload-safe direct-create transport, but the generated model shape is now driven
by ``SAM_OA.reference.json`` rather than by the legacy ArcadiaOA projection.

A versioned reference library and versioned instance name are used so an older
Level 1C baseline can coexist safely until its incremental migration is handled
in the next implementation step.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import uuid4

from sam_connection import SamSettings
from sam_full_projection import analyze_sam_projection, generate_sam_sysml_v2
from sam_level1_direct import _MetadataTolerantFactory, _rename_scripting_element
from sam_full_projection_writer import (
    create_projection_nodes,
    create_projection_packages,
    create_projection_relationships,
    create_projection_scenarios,
    create_sam_reference_definitions,
)
from sam_level1_sync import (
    SamLevel1SyncError,
    _documentation,
    _rows,
    _slug,
    build_level1_sync_plan,
)
from sam_level1_transactional import _descendant_named, _element_id, _load_project, _unique_match
from sam_reference_profile import DEFAULT_SAM_REFERENCE_PROFILE
from sam_reload_safe_factory import ReloadSafeFactory


SAM_REFERENCE_LIBRARY_PACKAGE = "MBSE_SAM_OA_Reference_Library_v2"
SAM_REFERENCE_LIBRARY_NAMESPACE = DEFAULT_SAM_REFERENCE_PROFILE.exported_library_package
SAM_REFERENCE_REQUIRED_CONCEPTS = (
    "OperationalScenario",
    "OperationalEntity",
    "OperationalActor",
    "OperationalCapability",
    "OperationalExchange",
    "CommunicationMean",
    "OperationalConstraint",
    "OperationalActivity",
)


def sam_full_projection_instance_package_name(model_name: str, snapshot_digest: str) -> str:
    """Return a versioned instance name that cannot alias a legacy Level 1 baseline."""
    return f"MBSE_Instance_SAM2_{_slug(model_name)}_{str(snapshot_digest)[:8]}"


def _matches(project: Any, name: str) -> list[Any]:
    return list(project.find_elements_by_name(name) or [])


def _unique_staging_name(project: Any, final_name: str) -> str:
    for _ in range(20):
        candidate = f"{final_name}__INCOMPLETE_{uuid4().hex[:8]}"
        if not _matches(project, candidate):
            return candidate
    raise SamLevel1SyncError(f"Could not allocate a unique staging name for {final_name!r}.")


def _definition_name(concept: str) -> str:
    return str(DEFAULT_SAM_REFERENCE_PROFILE.definition(concept).get("sysml_name") or concept)


def _library_status(project: Any) -> dict[str, Any]:
    package = _unique_match(project, SAM_REFERENCE_LIBRARY_PACKAGE)
    namespace = None
    definitions: dict[str, Any] = {}
    if package is not None:
        namespace = _descendant_named(project, package, SAM_REFERENCE_LIBRARY_NAMESPACE)
        if namespace is not None:
            for concept in SAM_REFERENCE_REQUIRED_CONCEPTS:
                definitions[concept] = _descendant_named(
                    project, namespace, _definition_name(concept)
                )
    missing = [
        concept for concept in SAM_REFERENCE_REQUIRED_CONCEPTS if definitions.get(concept) is None
    ]
    return {
        "loaded": package is not None and namespace is not None and not missing,
        "package": package,
        "package_id": _element_id(package) if package is not None else None,
        "namespace": namespace,
        "namespace_id": _element_id(namespace) if namespace is not None else None,
        "definitions": definitions,
        "missing_definitions": [_definition_name(concept) for concept in missing],
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
    """Create or reuse the versioned SAM reference library using direct PySAM creates."""
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
            "package_name": SAM_REFERENCE_LIBRARY_PACKAGE,
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
            "The final SAM reference library package exists but is incomplete. "
            "MBSE-App will not create a second final library with the same name."
        )

    root = project.get_root_package()
    staging_name = _unique_staging_name(project, SAM_REFERENCE_LIBRARY_PACKAGE)
    raw_factory = resolved_factory(project, connector)
    factory = _MetadataTolerantFactory(ReloadSafeFactory(project, raw_factory))
    library_package = None
    write_started = perf_counter()
    stage = "creating the managed SAM reference library package"
    try:
        library_package = factory.create_library_package(name=staging_name, owner=root)
        stage = "creating the SAM reference definitions"
        create_sam_reference_definitions(
            factory,
            library_package,
            DEFAULT_SAM_REFERENCE_PROFILE,
        )
        stage = "publishing the managed SAM reference library"
        _rename_scripting_element(project, library_package, SAM_REFERENCE_LIBRARY_PACKAGE)
    except Exception as exc:
        suffix = (
            f" A staging library named {staging_name!r} may remain in SAM and is not "
            "considered a valid managed library."
            if library_package is not None
            else ""
        )
        raise SamLevel1SyncError(
            f"SAM reference library direct creation failed while {stage}: {exc}.{suffix}"
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
            "The SAM reference library was published, but a fresh SAM read did not find "
            "all required definitions. Missing: " + ", ".join(verified["missing_definitions"])
        )

    return {
        "status": "loaded",
        "loaded": True,
        "sam_write_performed": True,
        "package_name": SAM_REFERENCE_LIBRARY_PACKAGE,
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
    """Publish one complete SAM-compatible OA baseline using the reference profile."""
    total_started = perf_counter()
    model = payload if isinstance(payload, dict) else {}
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    plan = build_level1_sync_plan(
        model,
        scenarios=scenario_rows,
        project_id=settings.project_id,
    )
    analysis = analyze_sam_projection(
        model,
        scenarios=scenario_rows,
        profile=DEFAULT_SAM_REFERENCE_PROFILE,
    )
    if plan["status"] != "ready" or not analysis.ready:
        raise SamLevel1SyncError(
            "Level 1 transfer is blocked because the snapshot cannot be represented by the SAM reference profile."
        )
    if expected_digest and expected_digest != plan["snapshot_digest"]:
        raise SamLevel1SyncError(
            "The model changed after the transfer plan was prepared. Review the new plan before sending."
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
            "The reusable SAM reference library could not be resolved before model instantiation."
        )
    definitions = library_state["definitions"]

    package_name = sam_full_projection_instance_package_name(
        plan["model_name"], plan["snapshot_digest"]
    )
    existing = _matches(project, package_name)
    if len(existing) > 1:
        raise SamLevel1SyncError(
            f"SAM contains more than one managed SAM2 instance named {package_name!r}."
        )
    if existing:
        return {
            **plan,
            "mode": "sam_compatible_full_projection",
            "package_name": package_name,
            "status": "already_synced",
            "sam_write_performed": False,
            "sam_package_id": _element_id(existing[0]),
            "completion_marker_required": False,
            "completion_marker_name": None,
            "incremental_sync_deferred": True,
            "library": {
                "status": library["status"],
                "loaded": True,
                "package_name": SAM_REFERENCE_LIBRARY_PACKAGE,
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
    model_package = None
    stage = "creating the SAM-compatible Level 1 instance package"
    write_started = perf_counter()
    try:
        model_package = factory.create_package(name=staging_name, owner=root)
        stage = "creating optional Level 1 instance metadata"
        _documentation(
            factory,
            model_package,
            "MBSE-App SAM-compatible full OA projection.\n"
            f"Model: {plan['model_name']}\n"
            f"Snapshot SHA-256: {plan['snapshot_digest']}\n"
            f"Shared library: {SAM_REFERENCE_LIBRARY_PACKAGE}\n"
            "Communication Mean projection: disabled for this phase.",
        )
        stage = "creating Structure, Requirements, and Scenarios packages"
        packages = create_projection_packages(
            factory, model_package, DEFAULT_SAM_REFERENCE_PROFILE
        )
        stage = "creating Operational Analysis usages"
        elements, characteristic_count = create_projection_nodes(
            factory,
            analysis=analysis,
            definitions=definitions,
            packages=packages,
        )
        stage = "creating Operational Analysis relationships"
        relationship_count = create_projection_relationships(
            factory,
            analysis=analysis,
            elements=elements,
            definitions=definitions,
            packages=packages,
        )
        stage = "creating Operational Scenarios"
        scenario_count, scenario_step_count = create_projection_scenarios(
            factory,
            analysis=analysis,
            elements=elements,
            definitions=definitions,
            packages=packages,
        )
        stage = "attaching the reviewed SysML v2 projection"
        factory.create_textual_representation(
            owner=model_package,
            represented_element=model_package,
            language="SysML v2",
            body=generate_sam_sysml_v2(
                model,
                scenarios=scenario_rows,
                drafts=[],
                profile=DEFAULT_SAM_REFERENCE_PROFILE,
            ),
        )
        stage = "publishing the completed SAM-compatible Level 1 instance"
        _rename_scripting_element(project, model_package, package_name)
    except Exception as exc:
        suffix = (
            f" A staging instance named {staging_name!r} may remain in SAM and is not considered synchronized."
            if model_package is not None
            else ""
        )
        raise SamLevel1SyncError(
            f"SAM compatible Level 1 direct creation failed while {stage}: {exc}.{suffix}"
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
            "The SAM-compatible Level 1 instance was published, but a fresh SAM read did not find exactly one final instance."
        )

    return {
        **plan,
        "mode": "sam_compatible_full_projection",
        "package_name": package_name,
        "status": "synced",
        "sam_write_performed": True,
        "sam_package_id": _element_id(verified_matches[0]),
        "completion_marker_required": False,
        "completion_marker_name": None,
        "incremental_sync_deferred": True,
        "library": {
            "status": library["status"],
            "loaded": True,
            "package_name": SAM_REFERENCE_LIBRARY_PACKAGE,
            "package_id": library_state["package_id"],
        },
        "created": {
            "source_elements": len(elements),
            "native_relationships": relationship_count,
            "ignored_relationships": len(analysis.ignored_edges),
            "characteristic_attributes": characteristic_count,
            "scenarios": scenario_count,
            "scenario_steps": scenario_step_count,
            "textual_level1_representation": 1,
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
