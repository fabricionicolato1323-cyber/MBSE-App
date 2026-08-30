"""Reliable direct-create writer for SAM Level 1B snapshots.

PySAM 0.3.1 documents Factory direct creation for new elements. Its transactional
creation path has known scripting-element inconsistencies and, against a live SAM
server, can accept the aggregate commit without leaving the created package behind.
This writer therefore uses the documented direct-create path and only publishes the
final package name after all required semantic content has been created.

PySAM reloads the scripting project after every direct create/update/delete commit.
The reload replaces the in-memory scripting element instances. All owners and
cross-element references are therefore rebound by stable element ID immediately
before each Factory call.

Auxiliary annotations are deliberately best-effort. A SAM/PySAM combination may
reject ``Documentation`` or ``TextualRepresentation`` even while accepting the
native SysML semantic elements. Such optional metadata must not make an otherwise
valid Level 1 semantic transfer fail.
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
from sam_reload_safe_factory import ReloadSafeFactory
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
    # The generated PySAM Element.name setter notifies the ModificationObserver,
    # commits the change and reloads the project. Use the public property rather
    # than mutating the backing field directly.
    current.name = name
    return _fresh_element(project, current)


class _MetadataTolerantFactory:
    """Delegate semantic creation while degrading unsupported metadata safely.

    The live SAM used for Gate 1B proved that Package direct creation works while
    the first Documentation direct creation returns HTTP 400. The PySAM 0.3.1
    metamodel exposes Documentation, but server-side acceptance can differ. This
    adapter probes a conservative Documentation payload once, then falls back to
    Comment, and finally disables annotations for the remainder of the transfer.
    """

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
        """Best-effort textual copy; the native semantic model remains authoritative."""
        try:
            return self._delegate.create_textual_representation(**kwargs)
        except Exception as exc:
            if not self._text_warning_recorded:
                self._text_warning_recorded = True
                self.warnings.append(
                    f"SAM rejected the optional TextualRepresentation; the native Level 1 semantic model was kept: {exc}"
                )
            return None


def _remove_incomplete_staging(project: Any, staging_name: str) -> int:
    """Delete only MBSE-App staging packages for the exact snapshot being retried."""
    removed = 0
    while True:
        matches = _matches(project, staging_name)
        if not matches:
            return removed
        element = _fresh_element(project, matches[0])

        delete = getattr(element, "delete", None)
        if callable(delete):
            # SysMLElement.delete() delegates to ModificationObserver.delete_element(),
            # which commits and reloads the project in direct mode.
            delete()
        elif hasattr(project, "elements") and element in project.elements:
            # Lightweight test-double path only.
            project.elements.remove(element)
        else:
            raise SamLevel1SyncError(
                f"SAM contains an incomplete Level 1 staging package named {staging_name!r}, "
                "but MBSE-App could not safely remove it. Remove that staging package in SAM "
                "before retrying."
            )

        removed += 1
        if removed > 20:
            raise SamLevel1SyncError(
                "Too many duplicate incomplete Level 1 staging packages were found; clean them "
                "manually in SAM before retrying."
            )


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
            f"SAM still contains an incomplete Level 1 staging package named {staging_name!r} "
            "after automatic cleanup. Remove that staging package in SAM before retrying."
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

    The package is initially named ``__INCOMPLETE``. Only after every required
    semantic element, relationship and scenario has been accepted is a completion
    marker created and the package renamed to its final Level 1 name. Optional
    annotations/text copies can be skipped when the server rejects those metadata
    types. A separate fresh-project verification is performed by the caller.
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

    existing_completed = _matches(project, package_name)
    existing_marker = _matches(project, marker_name)
    if existing_completed and existing_marker:
        return {
            **plan,
            "status": "already_synced",
            "sam_write_performed": False,
            "sam_package_id": _element_id(existing_completed[0]),
            "completion_marker_name": marker_name,
            "cleanup": {"removed_incomplete_staging_packages": 0},
            "metadata_warnings": [],
        }
    if existing_completed:
        raise SamLevel1SyncError(
            f"SAM contains a Level 1 package named {package_name!r}, but its completion "
            "marker is missing. Treat it as an incomplete previous transfer; remove that "
            "package in SAM before retrying."
        )

    removed_staging = _remove_incomplete_staging(project, staging_name)
    existing = _ensure_no_incomplete_snapshot(
        project,
        package_name=package_name,
        staging_name=staging_name,
        marker_name=marker_name,
    )
    if existing is not None:
        return {
            **plan,
            **existing,
            "cleanup": {"removed_incomplete_staging_packages": removed_staging},
            "metadata_warnings": [],
        }

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
                "PySAM returned from create_package(), but the staging package is not visible "
                "in the reloaded project. No Level 1 content will be sent."
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
        "cleanup": {"removed_incomplete_staging_packages": removed_staging},
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
