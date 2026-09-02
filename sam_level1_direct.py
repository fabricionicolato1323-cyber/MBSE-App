"""Reliable direct-create writer for SAM Level 1B snapshots.

PySAM 0.3.1 reloads a scripting project after each direct create/update/delete
commit. References are therefore rebound by stable ID through ReloadSafeFactory.
Incomplete attempts are intentionally never deleted automatically: the live SAM
used during Gate 1B can reject deletion of a partially populated package. Every
retry uses a unique staging package and only a final published package plus its
completion marker is considered synchronized.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

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
from sam_reload_safe_factory import ReloadSafeFactory
from sysml_v2 import generate_sysml_v2


def level1_completion_marker_name(snapshot_digest: str) -> str:
    """Return the server-visible marker proving a Level 1 snapshot finished."""
    digest = str(snapshot_digest or "").strip()
    return f"MBSE_Level1_Complete_{digest[:8] or 'unknown'}"


def level1_staging_package_name(
    package_name: str,
    attempt_id: str | None = None,
) -> str:
    """Return a staging name that can never be mistaken for a completed snapshot."""
    suffix = f"_{attempt_id}" if attempt_id else ""
    return f"{package_name}__INCOMPLETE{suffix}"


def _element_id(element: Any) -> str | None:
    for attr in ("id", "_id"):
        value = getattr(element, attr, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _matches(project: Any, name: str) -> list[Any]:
    return list(project.find_elements_by_name(name) or [])


def _fresh_element(project: Any, element: Any) -> Any:
    """Resolve an element against the current post-reload scripting project."""
    identity = _element_id(element)
    finder = getattr(project, "find_element_by_id", None)
    if identity and callable(finder):
        current = finder(identity)
        if current is not None:
            return current
    return element


def _rename_scripting_element(project: Any, element: Any, name: str) -> Any:
    """Persist a rename through the current PySAM scripting element observer."""
    current = _fresh_element(project, element)
    current.name = name
    return _fresh_element(project, current)


def _new_staging_name(project: Any, package_name: str) -> str:
    """Allocate a retry-safe staging name without deleting earlier attempts."""
    for _ in range(20):
        candidate = level1_staging_package_name(package_name, uuid4().hex[:8])
        if not _matches(project, candidate):
            return candidate
    raise SamLevel1SyncError(
        "Could not allocate a unique Level 1 staging package name after 20 attempts."
    )


class _MetadataTolerantFactory:
    """Delegate semantic creation while degrading unsupported metadata safely."""

    def __init__(self, delegate: Any):
        self._delegate = delegate
        self.warnings: list[str] = []
        self._documentation_mode = "probe"
        self._annotation_warning_recorded = False
        self._text_warning_recorded = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def _warn_annotation_once(self, message: str) -> None:
        if self._annotation_warning_recorded:
            return
        self._annotation_warning_recorded = True
        self.warnings.append(message)

    def create_documentation(self, **kwargs):
        """Create source annotation without allowing it to block semantics."""
        if self._documentation_mode == "disabled":
            return None

        documentation_kwargs = {
            key: value for key, value in kwargs.items() if key != "locale"
        }
        if self._documentation_mode in {"probe", "documentation"}:
            try:
                result = self._delegate.create_documentation(**documentation_kwargs)
                self._documentation_mode = "documentation"
                return result
            except Exception as exc:
                if self._documentation_mode == "documentation":
                    self._warn_annotation_once(
                        f"Some optional Documentation metadata was skipped by SAM: {exc}"
                    )
                    return None

        comment_kwargs = {
            "owner": kwargs.get("owner"),
            "body": kwargs.get("body"),
        }
        try:
            result = self._delegate.create_comment(**comment_kwargs)
            self._documentation_mode = "comment"
            self._warn_annotation_once(
                "SAM rejected Documentation metadata; MBSE-App used Comment annotations instead."
            )
            return result
        except Exception as exc:
            self._documentation_mode = "disabled"
            self._warn_annotation_once(
                f"SAM rejected optional Documentation/Comment metadata; annotations were skipped: {exc}"
            )
            return None

    def create_textual_representation(self, **kwargs):
        """Best-effort textual copy; native SysML elements remain authoritative."""
        try:
            return self._delegate.create_textual_representation(**kwargs)
        except Exception as exc:
            if not self._text_warning_recorded:
                self._text_warning_recorded = True
                self.warnings.append(
                    "SAM rejected the optional TextualRepresentation; the native "
                    f"Level 1 semantic model was kept: {exc}"
                )
            return None


def _retry_state(
    project: Any,
    package_name: str,
    marker_name: str,
) -> dict[str, Any] | None:
    """Return idempotent success only for an already fully published snapshot."""
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
            "marker is missing. Treat that final-name package as an incomplete previous "
            "publish and remove or rename it in SAM before retrying."
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

    Every attempt uses a unique ``__INCOMPLETE_<id>`` package. Earlier partial
    attempts are ignored rather than deleted. Only after every required semantic
    element, relationship and scenario has been accepted is a completion marker
    created and the current staging package renamed to the final Level 1 name.
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
            "Level 1 transfer is blocked because the snapshot contains unsupported "
            "or missing semantic content."
        )
    if expected_digest and expected_digest != plan["snapshot_digest"]:
        raise SamLevel1SyncError(
            "The model changed after the transfer plan was prepared. Review the new "
            "plan before sending."
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

    existing = _retry_state(project, package_name, marker_name)
    if existing is not None:
        return {
            **plan,
            **existing,
            "retry_policy": "unique_staging_no_delete",
            "cleanup": {"removed_incomplete_staging_packages": 0},
            "metadata_warnings": [],
        }

    # Old __INCOMPLETE packages are deliberately ignored. The live SAM used for
    # Gate 1B returns HTTP 400 when deleting a partially populated package, so a
    # new transfer must not depend on cleanup of earlier attempts.
    staging_name = _new_staging_name(project, package_name)

    root = project.get_root_package()
    raw_factory = factory_class(project, connector)
    reload_safe_factory = ReloadSafeFactory(project, raw_factory)
    factory = _MetadataTolerantFactory(reload_safe_factory)
    model_package = None
    stage = "creating the Level 1 staging package"
    textual_representation_count = 0

    try:
        model_package = factory.create_package(name=staging_name, owner=root)
        if not _matches(project, staging_name):
            raise SamLevel1SyncError(
                "PySAM returned from create_package(), but the new staging package is not "
                "visible in the reloaded project. No Level 1 content will be sent."
            )

        stage = "creating optional Level 1 package metadata"
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

        stage = "creating the optional Level 1 textual SysML v2 representation"
        sysml_text = generate_sysml_v2(model, scenarios=scenario_rows, drafts=[])
        textual_representation = factory.create_textual_representation(
            owner=model_package,
            represented_element=model_package,
            language="SysML v2",
            body=sysml_text,
        )
        textual_representation_count = 1 if textual_representation is not None else 0

        stage = "creating the Level 1 completion marker"
        factory.create_package(name=marker_name, owner=model_package)
        if not _matches(project, marker_name):
            raise SamLevel1SyncError(
                "The Level 1 completion marker was not visible after its direct create call."
            )

        stage = "publishing the completed Level 1 package"
        model_package = _rename_scripting_element(project, model_package, package_name)
        completed_matches = _matches(project, package_name)
        if not completed_matches:
            raise SamLevel1SyncError(
                "All Level 1 content was created, but the staging package could not be "
                "renamed to its final package name."
            )
    except SamLevel1SyncError:
        raise
    except Exception as exc:
        suffix = (
            f" A partial staging package named {staging_name!r} may remain in SAM; "
            "it is deliberately not considered synchronized. A retry will use a new "
            "staging package and will not attempt to delete this one."
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
        "retry_policy": "unique_staging_no_delete",
        "cleanup": {"removed_incomplete_staging_packages": 0},
        "metadata_warnings": list(factory.warnings),
        "created": {
            "source_elements": len(elements),
            "native_relationships": relationship_count,
            "characteristic_attributes": characteristic_count,
            "scenarios": scenario_count,
            "scenario_steps": scenario_step_count,
            "textual_level1_representation": textual_representation_count,
            "completion_marker": 1,
        },
    }
