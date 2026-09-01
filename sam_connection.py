"""Read-only Gate 0 smoke test for Ansys SAM / PySAM SysML2.

This module authenticates against the configured SAM organization, lists the
projects visible to the connected user, and only then loads a selected project.
It does not create, edit, commit, or publish model elements.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Mapping


REQUIRED_ENV_VARS = (
    "SAM_SERVER_URL",
    "SAM_ORGANIZATION_ID",
    "SAM_PROJECT_ID",
    "SAM_ACCESS_TOKEN",
)


class SamConfigurationError(RuntimeError):
    """Raised when the local SAM connection configuration is incomplete."""


@dataclass(frozen=True)
class SamSettings:
    server_url: str
    organization_id: str
    project_id: str
    access_token: str
    use_ssl: bool = True


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise SamConfigurationError(
        "SAM_USE_SSL must be true/false, yes/no, on/off, or 1/0."
    )


def load_env_file(path: str | Path = ".env") -> None:
    """Load a simple KEY=VALUE .env file without overwriting real env vars."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def _request_project_id_override() -> str:
    """Read an explicitly selected SAM project from the active Flask request."""
    try:
        from flask import has_request_context, request
    except ImportError:
        return ""

    if not has_request_context():
        return ""

    query_value = str(request.args.get("project_id") or "").strip()
    if query_value:
        return query_value

    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        body_value = str(payload.get("project_id") or "").strip()
        if body_value:
            return body_value
    return ""


def settings_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    load_dotenv: bool = True,
    env_path: str | Path = ".env",
) -> SamSettings:
    if load_dotenv and environ is None:
        load_env_file(env_path)

    source = os.environ if environ is None else environ
    missing = [name for name in REQUIRED_ENV_VARS if not source.get(name, "").strip()]
    if missing:
        raise SamConfigurationError(
            "Missing SAM configuration: " + ", ".join(missing)
        )

    selected_project = _request_project_id_override() or source["SAM_PROJECT_ID"].strip()

    return SamSettings(
        server_url=source["SAM_SERVER_URL"].strip().rstrip("/"),
        organization_id=source["SAM_ORGANIZATION_ID"].strip(),
        project_id=selected_project,
        access_token=source["SAM_ACCESS_TOKEN"].strip(),
        use_ssl=_parse_bool(source.get("SAM_USE_SSL"), default=True),
    )


def _element_name(element: Any) -> str:
    """Read a PySAM element name across dynamic/static representations."""
    for attr in ("name", "_name"):
        value = getattr(element, attr, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _element_id(element: Any) -> str | None:
    for attr in ("id", "_id"):
        value = getattr(element, attr, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _normalized_project_records(records: Any) -> list[dict[str, str]]:
    """Return only the project metadata needed by the project picker."""
    result: list[dict[str, str]] = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, Mapping):
            continue
        project_id = str(record.get("@id") or record.get("id") or "").strip()
        if not project_id:
            continue
        name = str(record.get("name") or project_id).strip() or project_id
        description = str(record.get("description") or "").strip()
        result.append({"id": project_id, "name": name, "description": description})
    result.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    return result


def _connect_to_organization(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
) -> tuple[Any, Any, list[dict[str, str]]]:
    """Authenticate in the organization and discover its visible projects first."""
    if connector_class is None or project_manager_class is None:
        try:
            from ansys.sam.sysml2 import (  # type: ignore[import-not-found]
                AnsysSysML2APIConnector,
                SysML2ProjectManager,
            )
        except ImportError as exc:
            raise RuntimeError(
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
    available_projects = _normalized_project_records(manager.get_projects())
    return connector, manager, available_projects


def list_available_projects(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
) -> list[dict[str, str]]:
    """List SysML v2 projects visible in the configured SAM organization."""
    _, _, available_projects = _connect_to_organization(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
    )
    return available_projects


def run_connection_test(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Discover organization projects first and load the selected project if valid.

    A stale ``SAM_PROJECT_ID`` no longer blocks the web project picker. In that
    case this function returns organization/project discovery metadata with
    ``project_selection_required=True`` and performs no project load. The UI can
    then ask the user to choose one of the projects that was actually returned by
    the configured organization and retry with that explicit project ID.
    """
    _, manager, available_projects = _connect_to_organization(
        settings,
        connector_class=connector_class,
        project_manager_class=project_manager_class,
    )

    available_ids = {item["id"] for item in available_projects}
    if settings.project_id not in available_ids:
        return {
            "server_url": settings.server_url,
            "organization_id": settings.organization_id,
            "configured_project_id": settings.project_id,
            "project_id": "",
            "project_name": "",
            "project_loaded": False,
            "project_selection_required": True,
            "available_projects": available_projects,
            "root_package_name": "",
            "root_package_id": None,
            "top_level_items": [],
            "write_performed": False,
        }

    project = manager.get_scripting_project(settings.project_id)
    if project is None:
        raise RuntimeError(
            f"Project {settings.project_id!r} is listed in SAM organization "
            f"{settings.organization_id!r}, but could not be loaded."
        )

    root_package = project.get_root_package()
    root_items = list(project.get_root() or [])
    project_name = str(project.get_name() or "").strip()
    actual_project_id = str(project.get_id() or settings.project_id).strip()

    return {
        "server_url": settings.server_url,
        "organization_id": settings.organization_id,
        "configured_project_id": settings.project_id,
        "project_id": actual_project_id,
        "project_name": project_name,
        "project_loaded": True,
        "project_selection_required": False,
        "available_projects": available_projects,
        "root_package_name": _element_name(root_package) or project_name,
        "root_package_id": _element_id(root_package),
        "top_level_items": [
            {
                "name": _element_name(item),
                "id": _element_id(item),
                "type": item.__class__.__name__,
            }
            for item in root_items
        ],
        "write_performed": False,
    }


def _print_success(result: Mapping[str, Any]) -> None:
    print("SAM Connection - Gate 0")
    print(f"Server ............. {result['server_url']}")
    print("Authentication ..... OK")
    print(f"Organization ....... {result['organization_id']}")
    if result.get("project_loaded"):
        project_label = result.get("project_name") or result["project_id"]
        print(f"Project ............ {project_label} ({result['project_id']})")
        root_name = result.get("root_package_name")
        if root_name:
            print(f"Root package ....... {root_name}")
        print("Project load ....... OK")
        print()
        print("Connection test: PASSED")
    else:
        projects = result.get("available_projects") or []
        print(f"Projects visible ... {len(projects)}")
        print("Project selection .. REQUIRED")
        print()
        print("Organization discovery: PASSED")
    print("No SAM model data was changed.")


def main() -> int:
    try:
        settings = settings_from_env()
        result = run_connection_test(settings)
    except Exception as exc:  # CLI boundary: present a concise diagnostic.
        print("SAM Connection - Gate 0")
        print(f"Connection test: FAILED - {type(exc).__name__}: {exc}")
        print("No SAM model data was changed.")
        return 1

    _print_success(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
