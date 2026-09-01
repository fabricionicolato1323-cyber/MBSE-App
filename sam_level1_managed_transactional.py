"""Fast transactional publisher for the SAM-compatible OA baseline.

The Commit 2 direct publisher is intentionally retained as a proven fallback,
but a full baseline contains enough native SysML elements that one direct commit
per element is unnecessarily expensive. This module builds the same SAM2 shape
inside PySAM transactional mode and sends it as one server commit per phase:
one commit for the reusable library when it is missing, then one commit for the
complete model baseline.

Optional source annotations and the textual representation are not transmitted
in this fast path. The native SAM elements and the local reviewed SysML Level 1
projection remain authoritative. Communication Mean remains library-only and is
not instantiated.
"""

from __future__ import annotations

from functools import wraps
import os
from time import perf_counter
from typing import Any

from sam_connection import SamSettings
from sam_full_projection import analyze_sam_projection
from sam_full_projection_writer import (
    create_projection_nodes,
    create_projection_packages,
    create_projection_relationships,
    create_projection_scenarios,
    create_sam_reference_definitions,
)
from sam_level1_managed_direct import (
    SAM_REFERENCE_LIBRARY_PACKAGE,
    _library_status,
    sam_full_projection_instance_package_name,
    sync_level1_to_sam_managed_direct,
)
from sam_level1_sync import SamLevel1SyncError, _rows, build_level1_sync_plan
from sam_level1_transactional import (
    TransactionalFactoryAdapter,
    _element_id,
    _load_project,
)
from sam_reference_profile import DEFAULT_SAM_REFERENCE_PROFILE


class SAM2TransactionalFactoryAdapter(TransactionalFactoryAdapter):
    """SAM2 transaction adapter for writable relationship fields and lean metadata."""

    def __getattr__(self, name: str) -> Any:
        # The source graph and reviewed textual SysML retain rich annotations.
        # Omitting per-element Documentation/Comment objects substantially reduces
        # payload size and avoids optional metadata affecting an atomic semantic commit.
        if name == "create_documentation":
            def semantic_documentation(*args, **kwargs):
                body = str(kwargs.get("body") or "")
                # Characteristic values are currently carried as compact metadata
                # attached to their AttributeUsage. Preserve only that semantic
                # metadata, using Comment because live SAM rejects Documentation.
                if '"source_characteristic"' in body:
                    return self.delegate.create_comment(
                        owner=kwargs.get("owner"),
                        body=body,
                    )
                return None
            return semantic_documentation

        if name == "create_comment":
            def skip_optional_comment(*args, **kwargs):
                return None
            return skip_optional_comment

        # The live SAM/PySAM combination used by this PoC does not reliably accept
        # native Succession creation. This matches the proven direct transport:
        # scenario order remains normative in the local SysML textual projection.
        if name == "create_succession":
            def skip_succession(*args, **kwargs):
                return None
            return skip_succession

        # ReferenceUsage.referencedFeature is a derived projection in the live SAM
        # metamodel. Persist LOCATED_IN through owned ReferenceSubsetting elements.
        if name == "create_reference_usage":
            target = getattr(self.delegate, name)

            @wraps(target)
            def create_reference_usage(*args, **kwargs):
                referenced_value = kwargs.get("referenced_feature")
                if referenced_value is None or args:
                    return target(*args, **kwargs)

                if isinstance(referenced_value, (list, tuple, set)):
                    referenced = [item for item in referenced_value if item is not None]
                else:
                    referenced = [referenced_value]
                if not referenced:
                    return target(*args, **kwargs)

                base_kwargs = dict(kwargs)
                base_kwargs.pop("referenced_feature", None)
                usage = target(**base_kwargs)
                for referenced_feature in referenced:
                    self.delegate.create_reference_subsetting(
                        owner=usage,
                        referencing_feature=usage,
                        referenced_feature=referenced_feature,
                    )
                return usage

            return create_reference_usage

        return super().__getattr__(name)


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


def ensure_sam_reference_library_transactional(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Create/reuse the SAM2 reference library with at most one server commit."""
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
            "server_commits": 0,
            "timings": {
                "connection_seconds": round(connection_seconds, 3),
                "build_seconds": 0.0,
                "commit_seconds": 0.0,
                "verification_seconds": 0.0,
                "total_seconds": round(perf_counter() - total_started, 3),
            },
        }
    if current["package"] is not None:
        raise SamLevel1SyncError(
            "The final SAM reference library package exists but is incomplete. "
            "MBSE-App will not create a duplicate."
        )

    root = project.get_root_package()
    factory = SAM2TransactionalFactoryAdapter(resolved_factory(project, connector))
    build_started = perf_counter()
    project.start_transactional_mode()
    try:
        library_package = factory.create_library_package(
            name=SAM_REFERENCE_LIBRARY_PACKAGE,
            owner=root,
        )
        create_sam_reference_definitions(
            factory,
            library_package,
            DEFAULT_SAM_REFERENCE_PROFILE,
        )
        build_seconds = perf_counter() - build_started
        commit_started = perf_counter()
        project.stop_transactional_mode()
        commit_seconds = perf_counter() - commit_started
    except Exception as exc:
        raise SamLevel1SyncError(
            "SAM reference library transactional creation failed: "
            f"{exc}. The fast writer does not intentionally publish an incomplete "
            "managed library."
        ) from exc

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
            "SAM accepted the reference-library transaction, but a fresh read did "
            "not find the complete SAM2 library."
        )

    return {
        "status": "loaded",
        "loaded": True,
        "sam_write_performed": True,
        "package_name": SAM_REFERENCE_LIBRARY_PACKAGE,
        "package_id": verified["package_id"],
        "server_commits": 1,
        "timings": {
            "connection_seconds": round(connection_seconds, 3),
            "build_seconds": round(build_seconds, 3),
            "commit_seconds": round(commit_seconds, 3),
            "verification_seconds": round(verification_seconds, 3),
            "total_seconds": round(perf_counter() - total_started, 3),
        },
    }


def _verified_instance(project: Any, package_name: str) -> Any:
    matches = list(project.find_elements_by_name(package_name) or [])
    if len(matches) != 1:
        raise SamLevel1SyncError(
            "A fresh SAM read did not find exactly one completed SAM2 baseline "
            f"named {package_name!r}."
        )
    return matches[0]


def sync_level1_to_sam_managed_transactional(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None,
    settings: SamSettings,
    expected_digest: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Publish the SAM-compatible full OA baseline in one model transaction."""
    transport_override = os.getenv("SAM_BASELINE_TRANSPORT", "transactional").strip().casefold()
    if transport_override == "direct":
        return sync_level1_to_sam_managed_direct(
            payload,
            scenarios=scenarios,
            settings=settings,
            expected_digest=expected_digest,
            connector_class=connector_class,
            project_manager_class=project_manager_class,
            factory_class=factory_class,
        )
    if transport_override not in {"", "transactional", "batch"}:
        raise SamLevel1SyncError(
            "SAM_BASELINE_TRANSPORT must be 'transactional' (default) or 'direct'."
        )

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
            "Level 1 transfer is blocked because the snapshot cannot be represented "
            "by the SAM reference profile."
        )
    if expected_digest and expected_digest != plan["snapshot_digest"]:
        raise SamLevel1SyncError(
            "The model changed after the transfer plan was prepared. Review the new "
            "plan before sending."
        )

    library = ensure_sam_reference_library_transactional(
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
            "The reusable SAM2 reference library could not be resolved before "
            "model instantiation."
        )
    definitions = library_state["definitions"]

    package_name = sam_full_projection_instance_package_name(
        plan["model_name"],
        plan["snapshot_digest"],
    )
    existing = list(project.find_elements_by_name(package_name) or [])
    if len(existing) > 1:
        raise SamLevel1SyncError(
            f"SAM contains more than one managed SAM2 instance named {package_name!r}."
        )
    if existing:
        return {
            **plan,
            "mode": "sam_compatible_full_projection_transactional",
            "transport": "transactional_batch",
            "package_name": package_name,
            "status": "already_synced",
            "sam_write_performed": False,
            "sam_package_id": _element_id(existing[0]),
            "completion_marker_required": False,
            "completion_marker_name": None,
            "incremental_sync_deferred": True,
            "server_commits": 0,
            "library": {
                "status": library["status"],
                "loaded": True,
                "package_name": SAM_REFERENCE_LIBRARY_PACKAGE,
                "package_id": library_state["package_id"],
            },
            "timings": {
                "library_seconds": round(
                    float(library.get("timings", {}).get("total_seconds", 0.0)), 3
                ),
                "connection_seconds": round(connection_seconds, 3),
                "build_seconds": 0.0,
                "commit_seconds": 0.0,
                "verification_seconds": 0.0,
                "total_seconds": round(perf_counter() - total_started, 3),
            },
        }

    root = project.get_root_package()
    factory = SAM2TransactionalFactoryAdapter(resolved_factory(project, connector))
    build_started = perf_counter()
    project.start_transactional_mode()
    try:
        model_package = factory.create_package(name=package_name, owner=root)
        packages = create_projection_packages(
            factory,
            model_package,
            DEFAULT_SAM_REFERENCE_PROFILE,
        )
        elements, characteristic_count = create_projection_nodes(
            factory,
            analysis=analysis,
            definitions=definitions,
            packages=packages,
        )
        relationship_count = create_projection_relationships(
            factory,
            analysis=analysis,
            elements=elements,
            definitions=definitions,
            packages=packages,
        )
        scenario_count, scenario_step_count = create_projection_scenarios(
            factory,
            analysis=analysis,
            elements=elements,
            definitions=definitions,
            packages=packages,
        )
        build_seconds = perf_counter() - build_started
        commit_started = perf_counter()
        project.stop_transactional_mode()
        commit_seconds = perf_counter() - commit_started
    except Exception as exc:
        raise SamLevel1SyncError(
            "SAM-compatible Level 1 transactional publish failed: "
            f"{exc}. No per-element direct-write retry was attempted automatically."
        ) from exc

    verify_started = perf_counter()
    _, _, verified_project, _ = _fresh_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=resolved_factory,
    )
    verified_instance = _verified_instance(verified_project, package_name)
    verification_seconds = perf_counter() - verify_started

    return {
        **plan,
        "mode": "sam_compatible_full_projection_transactional",
        "transport": "transactional_batch",
        "package_name": package_name,
        "status": "synced",
        "sam_write_performed": True,
        "sam_package_id": _element_id(verified_instance),
        "completion_marker_required": False,
        "completion_marker_name": None,
        "incremental_sync_deferred": True,
        "server_commits": 1 + int(bool(library.get("sam_write_performed"))),
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
            "textual_level1_representation": 0,
            "optional_source_annotations": 0,
            "characteristic_metadata_comments": characteristic_count,
            "visible_completion_marker": 0,
        },
        "timings": {
            "library_seconds": round(
                float(library.get("timings", {}).get("total_seconds", 0.0)), 3
            ),
            "connection_seconds": round(connection_seconds, 3),
            "build_seconds": round(build_seconds, 3),
            "commit_seconds": round(commit_seconds, 3),
            "verification_seconds": round(verification_seconds, 3),
            "total_seconds": round(perf_counter() - total_started, 3),
        },
    }
