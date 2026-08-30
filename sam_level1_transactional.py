"""Fast, idempotent SAM Level 1 transport with a reusable ArcadiaOA library.

The transport is deliberately split into two server transactions:

1. ``MBSE_ArcadiaOA_Library_v1`` is created once and contains the reusable
   SysML v2 definitions used by Operational Analysis models.
2. Each confirmed model snapshot is created as a separate
   ``MBSE_Instance_<model>_<digest>`` package that references those definitions.

Unlike the legacy direct writer, Factory.create_* calls execute while PySAM is in
transaction mode. Element creation is therefore local until
``stop_transactional_mode()`` commits the complete phase to SAM, avoiding one
HTTP commit + project reload per model element.
"""

from __future__ import annotations

from functools import wraps
from time import perf_counter
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
    _slug,
    build_level1_sync_plan,
)

ARCADIA_OA_LIBRARY_PACKAGE = "MBSE_ArcadiaOA_Library_v1"
ARCADIA_OA_LIBRARY_MARKER = "MBSE_ArcadiaOA_Library_Complete_v1"
ARCADIA_OA_NAMESPACE = "ArcadiaOA"

_REQUIRED_DEFINITIONS = (
    "OperationalEntity",
    "OperationalActor",
    "OperationalActivity",
    "OperationalInformation",
    "OperationalExchange",
    "CommunicationMean",
    "OperationalScenario",
    "OperationalCapability",
)


def _element_id(value: Any) -> str | None:
    for attr in ("id", "_id"):
        try:
            candidate = getattr(value, attr, None)
        except Exception:
            candidate = None
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return None


def _first(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _normalize_simple_call(
    name: str,
    kwargs: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Translate strict SAM relationship calls to writable native properties."""
    normalized = dict(kwargs)
    if name == "create_subclassification":
        normalized.pop("source", None)
        normalized.pop("target", None)
        return name, normalized

    if name == "create_allocation_usage":
        satisfied_requirement = normalized.get("source_feature") or _first(
            normalized.get("source")
        )
        satisfying_feature = _first(normalized.get("target_feature")) or _first(
            normalized.get("target")
        )
        if satisfied_requirement is None or satisfying_feature is None:
            raise SamLevel1SyncError(
                "Capability-support transport requires both an Operational Capability "
                "and an Operational Activity."
            )
        transport = {
            "name": normalized.get("name"),
            "owner": normalized.get("owner"),
            "satisfied_requirement": satisfied_requirement,
            "satisfying_feature": satisfying_feature,
        }
        return (
            "create_satisfy_requirement_usage",
            {key: value for key, value in transport.items() if value is not None},
        )

    return name, normalized


class TransactionalFactoryAdapter:
    """Apply SAM-safe relationship payloads without direct-mode reload handling."""

    _CONNECTOR_METHODS = {"create_connection_usage", "create_flow_connection_usage"}
    _DERIVED_CONNECTOR_KEYS = {
        "source",
        "target",
        "source_feature",
        "target_feature",
        "related_feature",
        "connector_end",
    }

    def __init__(self, delegate: Any):
        self.delegate = delegate

    def _create_binary_connector(self, name: str, kwargs: dict[str, Any]) -> Any:
        raw = dict(kwargs)
        source = raw.get("source_feature") or _first(raw.get("source"))
        target = _first(raw.get("target_feature")) or _first(raw.get("target"))
        if source is None or target is None:
            raise SamLevel1SyncError(f"{name} requires both source and target features.")

        base_kwargs = {
            key: value
            for key, value in raw.items()
            if key not in self._DERIVED_CONNECTOR_KEYS
        }
        connector = getattr(self.delegate, name)(**base_kwargs)
        base_name = str(raw.get("name") or "connector").strip() or "connector"
        for role, endpoint in (("source", source), ("target", target)):
            end = self.delegate.create_reference_usage(
                name=f"{base_name}__{role}_end",
                owner=connector,
                is_end=True,
            )
            self.delegate.create_reference_subsetting(
                owner=end,
                referencing_feature=end,
                referenced_feature=endpoint,
            )
        return connector

    def __getattr__(self, name: str) -> Any:
        target = getattr(self.delegate, name)
        if not name.startswith("create_") or not callable(target):
            return target

        @wraps(target)
        def transactional_create(*args, **kwargs):
            if args:
                return target(*args, **kwargs)
            if name in self._CONNECTOR_METHODS:
                return self._create_binary_connector(name, kwargs)
            transport_name, normalized = _normalize_simple_call(name, kwargs)
            return getattr(self.delegate, transport_name)(**normalized)

        return transactional_create


def _project_elements(project: Any) -> list[Any]:
    env = getattr(project, "_env", None)
    if isinstance(env, dict):
        return list(env.values())
    elements = getattr(project, "elements", None)
    if isinstance(elements, list):
        return list(elements)
    return []


def _attribute_values(value: Any, attrs: tuple[str, ...]) -> list[Any]:
    """Collect mapped values without assuming PySAM's JSON naming convention.

    PySAM's scripting mapper stores server JSON keys verbatim behind an underscore
    (for example ``owningNamespace`` becomes ``_owningNamespace``), while test
    doubles and some native classes expose snake_case properties. Fresh SAM reloads
    can therefore differ from the objects created in the active transaction.
    """
    result: list[Any] = []
    for attr in attrs:
        try:
            candidate = getattr(value, attr, None)
        except Exception:
            candidate = None
        if candidate is None:
            continue
        if isinstance(candidate, (list, tuple, set)):
            result.extend(item for item in candidate if item is not None)
        else:
            result.append(candidate)
    return result


def _owner_candidates(value: Any) -> list[Any]:
    return _attribute_values(
        value,
        (
            "owner",
            "_owner",
            "owning_namespace",
            "_owning_namespace",
            "owningNamespace",
            "_owningNamespace",
            "owning_type",
            "_owning_type",
            "owningType",
            "_owningType",
        ),
    )


def _is_owned_by(value: Any, owner: Any) -> bool:
    owner_id = _element_id(owner)
    for owner_value in _owner_candidates(value):
        if owner_value is owner:
            return True
        if owner_id and _element_id(owner_value) == owner_id:
            return True
        if owner_id and isinstance(owner_value, str) and owner_value == owner_id:
            return True
    return False


def _resolve_project_value(project: Any, value: Any) -> Any:
    """Resolve ID-only values emitted by the scripting mapper when possible."""
    if not isinstance(value, str):
        return value
    finder = getattr(project, "find_element_by_id", None)
    if callable(finder):
        try:
            resolved = finder(value)
        except Exception:
            resolved = None
        if resolved is not None:
            return resolved
    for item in _project_elements(project):
        if _element_id(item) == value:
            return item
    return value


def _children(project: Any, owner: Any) -> list[Any]:
    """Return children across transactional and freshly reloaded PySAM shapes.

    Never return early just because an ``ownedElement`` collection exists: SAM can
    reload that derived collection as empty while each child still carries an
    ``owningNamespace`` reference. We therefore merge both directions.
    """
    candidates = _attribute_values(
        owner,
        (
            "owned_element",
            "_owned_element",
            "ownedElement",
            "_ownedElement",
            "owned_member",
            "_owned_member",
            "ownedMember",
            "_ownedMember",
        ),
    )
    candidates.extend(item for item in _project_elements(project) if _is_owned_by(item, owner))

    result: list[Any] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = _resolve_project_value(project, candidate)
        identity = _element_id(resolved)
        if identity is None and isinstance(resolved, str):
            identity = f"id:{resolved}"
        if identity is None:
            identity = f"object:{id(resolved)}"
        if identity in seen:
            continue
        seen.add(identity)
        result.append(resolved)
    return result


def _element_name(value: Any) -> str:
    for attr in ("name", "_name"):
        try:
            candidate = getattr(value, attr, None)
        except Exception:
            candidate = None
        if candidate is not None:
            return str(candidate)
    return ""


def _descendant_named(project: Any, owner: Any, name: str) -> Any | None:
    queue = list(_children(project, owner))
    seen: set[str] = set()
    while queue:
        current = queue.pop(0)
        identity = _element_id(current) or str(id(current))
        if identity in seen:
            continue
        seen.add(identity)
        if _element_name(current) == name:
            return current
        queue.extend(_children(project, current))
    return None


def _unique_match(project: Any, name: str) -> Any | None:
    matches = list(project.find_elements_by_name(name) or [])
    if len(matches) > 1:
        raise SamLevel1SyncError(
            f"SAM contains more than one element named {name!r}. Resolve the duplicate "
            "before continuing the managed Level 1 transfer."
        )
    return matches[0] if matches else None


def _load_project(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> tuple[Any, Any, Any, type[Any]]:
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
    return connector, manager, project, factory_class


def _library_status_from_project(project: Any) -> dict[str, Any]:
    package = _unique_match(project, ARCADIA_OA_LIBRARY_PACKAGE)
    marker = _unique_match(project, ARCADIA_OA_LIBRARY_MARKER)
    definitions: dict[str, Any] = {}
    namespace = None
    marker_in_package = None
    if package is not None:
        marker_in_package = _descendant_named(project, package, ARCADIA_OA_LIBRARY_MARKER)
        namespace = _descendant_named(project, package, ARCADIA_OA_NAMESPACE)
        if namespace is not None:
            for name in _REQUIRED_DEFINITIONS:
                definitions[name] = _descendant_named(project, namespace, name)

    missing = [name for name in _REQUIRED_DEFINITIONS if definitions.get(name) is None]
    loaded = (
        package is not None
        and marker is not None
        and marker_in_package is not None
        and namespace is not None
        and not missing
    )
    return {
        "loaded": loaded,
        "package_name": ARCADIA_OA_LIBRARY_PACKAGE,
        "package_id": _element_id(package) if package is not None else None,
        "namespace_name": ARCADIA_OA_NAMESPACE,
        "namespace_id": _element_id(namespace) if namespace is not None else None,
        "completion_marker_name": ARCADIA_OA_LIBRARY_MARKER,
        "completion_marker_id": _element_id(marker) if marker is not None else None,
        "completion_marker_scoped": marker_in_package is not None,
        "missing_definitions": missing,
        "definitions": definitions,
        "package": package,
        "namespace": namespace,
    }


def _library_diagnostic(status: dict[str, Any]) -> str:
    missing = status.get("missing_definitions") or []
    parts = [
        f"package={'yes' if status.get('package_id') else 'no'}",
        f"marker={'yes' if status.get('completion_marker_id') else 'no'}",
        f"marker_scoped={'yes' if status.get('completion_marker_scoped') else 'no'}",
        f"namespace={'yes' if status.get('namespace_id') else 'no'}",
    ]
    if missing:
        parts.append("missing=" + ",".join(str(item) for item in missing))
    return "; ".join(parts)


def get_arcadia_oa_library_status(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Read whether the managed reusable ArcadiaOA library is complete in SAM."""
    started = perf_counter()
    _, _, project, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    status = _library_status_from_project(project)
    status.pop("definitions", None)
    status.pop("package", None)
    status.pop("namespace", None)
    status["read_seconds"] = round(perf_counter() - started, 3)
    return status


def ensure_arcadia_oa_library(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Create the reusable library once, using one PySAM transaction."""
    total_started = perf_counter()
    connect_started = perf_counter()
    connector, _, project, resolved_factory = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    connect_seconds = perf_counter() - connect_started
    current = _library_status_from_project(project)
    if current["loaded"]:
        return {
            "status": "already_loaded",
            "loaded": True,
            "sam_write_performed": False,
            "package_name": ARCADIA_OA_LIBRARY_PACKAGE,
            "package_id": current["package_id"],
            "completion_marker_name": ARCADIA_OA_LIBRARY_MARKER,
            "timings": {
                "connection_seconds": round(connect_seconds, 3),
                "build_seconds": 0.0,
                "commit_seconds": 0.0,
                "total_seconds": round(perf_counter() - total_started, 3),
            },
        }
    if current["package"] is not None or current["completion_marker_id"] is not None:
        raise SamLevel1SyncError(
            "The managed ArcadiaOA library is present in SAM but could not be verified "
            "as complete after reload. MBSE-App will not create a duplicate. "
            f"Diagnostic: {_library_diagnostic(current)}"
        )

    root = project.get_root_package()
    raw_factory = resolved_factory(project, connector)
    factory = TransactionalFactoryAdapter(raw_factory)
    build_started = perf_counter()
    project.start_transactional_mode()
    try:
        library_package = factory.create_library_package(
            name=ARCADIA_OA_LIBRARY_PACKAGE,
            owner=root,
        )
        _create_library_definitions(factory, library_package)
        factory.create_package(name=ARCADIA_OA_LIBRARY_MARKER, owner=library_package)
        build_seconds = perf_counter() - build_started
        commit_started = perf_counter()
        project.stop_transactional_mode()
        commit_seconds = perf_counter() - commit_started
    except Exception as exc:
        raise SamLevel1SyncError(f"SAM ArcadiaOA library transaction failed: {exc}") from exc

    verify_started = perf_counter()
    # SysML2ProjectManager caches ScriptingProject instances by project_id. Calling
    # get_scripting_project() on the manager used before the commit therefore is not
    # an independent server verification. Build a new connector + manager so the
    # project metadata, branch head, and elements are read again from SAM.
    _, _, reloaded, _ = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=resolved_factory,
    )
    verified = _library_status_from_project(reloaded)
    if not verified["loaded"]:
        raise SamLevel1SyncError(
            "SAM accepted the ArcadiaOA library transaction, but an uncached server "
            "verification did not find a complete managed library. MBSE-App will not "
            "create a duplicate on this transfer. "
            f"Diagnostic: {_library_diagnostic(verified)}"
        )
    verify_seconds = perf_counter() - verify_started
    return {
        "status": "loaded",
        "loaded": True,
        "sam_write_performed": True,
        "package_name": ARCADIA_OA_LIBRARY_PACKAGE,
        "package_id": verified["package_id"],
        "completion_marker_name": ARCADIA_OA_LIBRARY_MARKER,
        "timings": {
            "connection_seconds": round(connect_seconds, 3),
            "build_seconds": round(build_seconds, 3),
            "commit_seconds": round(commit_seconds, 3),
            "verification_seconds": round(verify_seconds, 3),
            "total_seconds": round(perf_counter() - total_started, 3),
        },
    }


def level1_completion_marker_name(snapshot_digest: str) -> str:
    digest = str(snapshot_digest or "").strip()
    return f"MBSE_Instance_Complete_{digest[:8] or 'unknown'}"


def level1_instance_package_name(model_name: str, snapshot_digest: str) -> str:
    return f"MBSE_Instance_{_slug(model_name)}_{str(snapshot_digest)[:8]}"


def _resolved_library_definitions(project: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    status = _library_status_from_project(project)
    if not status["loaded"]:
        raise SamLevel1SyncError(
            "The ArcadiaOA library must be loaded and verified before model instantiation. "
            f"Diagnostic: {_library_diagnostic(status)}"
        )
    return status["definitions"], status


def sync_level1_to_sam_transactional(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None,
    settings: SamSettings,
    expected_digest: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Load the shared library if needed, then commit one model instantiation."""
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

    library = ensure_arcadia_oa_library(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )

    connect_started = perf_counter()
    connector, _, project, resolved_factory = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    connect_seconds = perf_counter() - connect_started
    definitions, library_state = _resolved_library_definitions(project)

    package_name = level1_instance_package_name(plan["model_name"], plan["snapshot_digest"])
    marker_name = level1_completion_marker_name(plan["snapshot_digest"])
    existing = list(project.find_elements_by_name(package_name) or [])
    markers = list(project.find_elements_by_name(marker_name) or [])
    if existing and markers:
        return {
            **plan,
            "mode": "transactional_library_then_instantiation",
            "package_name": package_name,
            "status": "already_synced",
            "sam_write_performed": False,
            "sam_package_id": _element_id(existing[0]),
            "completion_marker_name": marker_name,
            "library": {key: value for key, value in library.items() if key != "timings"},
            "timings": {
                "library_seconds": round(float(library.get("timings", {}).get("total_seconds", 0.0)), 3),
                "connection_seconds": round(connect_seconds, 3),
                "build_seconds": 0.0,
                "commit_seconds": 0.0,
                "total_seconds": round(perf_counter() - total_started, 3),
            },
        }
    if existing or markers:
        raise SamLevel1SyncError(
            f"SAM contains an incomplete managed instantiation for digest "
            f"{plan['snapshot_digest'][:8]}. Resolve that package/marker before retrying."
        )

    root = project.get_root_package()
    raw_factory = resolved_factory(project, connector)
    factory = TransactionalFactoryAdapter(raw_factory)
    nodes = _rows(model.get("nodes"))
    edges = _rows(model.get("edges"))
    source_node_by_id = {str(node.get("id")): node for node in nodes}

    build_started = perf_counter()
    project.start_transactional_mode()
    try:
        model_package = factory.create_package(name=package_name, owner=root)
        _documentation(
            factory,
            model_package,
            "MBSE-App Level 1 model instantiation.\n"
            f"Model: {plan['model_name']}\n"
            f"Snapshot SHA-256: {plan['snapshot_digest']}\n"
            f"Shared library: {ARCADIA_OA_LIBRARY_PACKAGE}\n"
            f"Source elements: {plan['counts']['elements']}\n"
            f"Source relationships: {plan['counts']['relationships']}\n"
            f"Operational scenarios: {plan['counts']['scenarios']}",
        )
        elements, structure, behavior, characteristic_count = _create_source_nodes(
            factory,
            nodes=nodes,
            edges=edges,
            definitions=definitions,
            model_package=model_package,
        )
        relationship_count = _create_relationships(
            factory,
            edges=edges,
            elements=elements,
            definitions=definitions,
            model_package=model_package,
            structure=structure,
            behavior=behavior,
        )
        scenario_count, scenario_step_count = _create_scenarios(
            factory,
            scenarios=scenario_rows,
            source_nodes=source_node_by_id,
            definitions=definitions,
            model_package=model_package,
        )
        factory.create_package(name=marker_name, owner=model_package)
        build_seconds = perf_counter() - build_started
        commit_started = perf_counter()
        project.stop_transactional_mode()
        commit_seconds = perf_counter() - commit_started
    except Exception as exc:
        raise SamLevel1SyncError(
            f"SAM Level 1 instantiation transaction failed: {exc}. No new managed "
            "__INCOMPLETE package is created by the transactional writer."
        ) from exc

    return {
        **plan,
        "mode": "transactional_library_then_instantiation",
        "package_name": package_name,
        "status": "synced",
        "sam_write_performed": True,
        "sam_package_id": _element_id(model_package),
        "completion_marker_name": marker_name,
        "library": {
            "status": library.get("status"),
            "loaded": True,
            "package_name": ARCADIA_OA_LIBRARY_PACKAGE,
            "package_id": library_state.get("package_id"),
        },
        "created": {
            "source_elements": len(elements),
            "native_relationships": relationship_count,
            "characteristic_attributes": characteristic_count,
            "scenarios": scenario_count,
            "scenario_steps": scenario_step_count,
            "textual_level1_representation": 0,
            "completion_marker": 1,
        },
        "timings": {
            "library_seconds": round(float(library.get("timings", {}).get("total_seconds", 0.0)), 3),
            "connection_seconds": round(connect_seconds, 3),
            "build_seconds": round(build_seconds, 3),
            "commit_seconds": round(commit_seconds, 3),
            "total_seconds": round(perf_counter() - total_started, 3),
        },
    }