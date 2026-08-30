"""Post-write verification for SAM Level 1B transfers."""

from __future__ import annotations

from typing import Any

from sam_connection import SamSettings
from sam_level1_direct import level1_completion_marker_name, sync_level1_to_sam_direct
from sam_level1_sync import SamLevel1SyncError


def _element_id(element: Any) -> str | None:
    for attr in ("id", "_id"):
        value = getattr(element, attr, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _load_project(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
):
    if connector_class is None or project_manager_class is None:
        try:
            from ansys.sam.sysml2 import AnsysSysML2APIConnector, SysML2ProjectManager
        except ImportError as exc:  # pragma: no cover - optional dependency boundary.
            raise SamLevel1SyncError(
                "PySAM SysML2 is not installed. Run: python -m pip install -r requirements.txt"
            ) from exc
        connector_class = connector_class or AnsysSysML2APIConnector
        project_manager_class = project_manager_class or SysML2ProjectManager

    connector = connector_class(
        server_url=settings.server_url,
        organization_id=settings.organization_id,
        token=settings.access_token,
        use_ssl=settings.use_ssl,
    )
    manager = project_manager_class(connector=connector)
    project = manager.get_scripting_project(settings.project_id)
    if project is None:
        raise SamLevel1SyncError(
            "Post-write verification could not reload the configured SAM project."
        )
    return project


def verify_level1_package(
    settings: SamSettings,
    package_name: str,
    *,
    snapshot_digest: str | None = None,
    completion_marker_name: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Reload SAM and prove that both package and completion marker exist."""
    project = _load_project(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
    )
    matches = list(project.find_elements_by_name(package_name) or [])
    if not matches:
        raise SamLevel1SyncError(
            "SAM accepted the transfer call, but the Level 1 package was not found after "
            "the project was reloaded. The transfer is therefore not marked as synchronized."
        )

    marker_name = completion_marker_name
    if not marker_name and snapshot_digest:
        marker_name = level1_completion_marker_name(snapshot_digest)
    if marker_name:
        marker_matches = list(project.find_elements_by_name(marker_name) or [])
        if not marker_matches:
            raise SamLevel1SyncError(
                "The Level 1 package exists in SAM, but its completion marker was not found "
                "after a fresh project reload. The package is treated as incomplete and is "
                "not marked as synchronized."
            )
    else:
        marker_matches = []

    return {
        "verified_in_sam": True,
        "verified_package_name": package_name,
        "verified_package_id": _element_id(matches[0]),
        "verified_match_count": len(matches),
        "verified_completion_marker_name": marker_name,
        "verified_completion_marker_id": (
            _element_id(marker_matches[0]) if marker_matches else None
        ),
    }


def sync_level1_to_sam_verified(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None,
    settings: SamSettings,
    expected_digest: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Run direct Level 1B creation and return success only after a fresh SAM read verifies it."""
    result = sync_level1_to_sam_direct(
        payload,
        scenarios=scenarios,
        settings=settings,
        expected_digest=expected_digest,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
        factory_class=factory_class,
    )
    if result.get("status") not in {"synced", "already_synced"}:
        return result
    verification = verify_level1_package(
        settings,
        str(result.get("package_name") or ""),
        snapshot_digest=str(result.get("snapshot_digest") or ""),
        completion_marker_name=str(result.get("completion_marker_name") or "") or None,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
    )
    result.update(verification)
    if verification.get("verified_package_id"):
        result["sam_package_id"] = verification["verified_package_id"]
    return result
