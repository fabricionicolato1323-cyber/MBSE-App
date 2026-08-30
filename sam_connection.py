"""Read-only Gate 0 smoke test for Ansys SAM / PySAM SysML2.

This module only authenticates and loads an existing SAM project. It does not
create, edit, commit, or publish model elements.
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

    return SamSettings(
        server_url=source["SAM_SERVER_URL"].strip().rstrip("/"),
        organization_id=source["SAM_ORGANIZATION_ID"].strip(),
        project_id=source["SAM_PROJECT_ID"].strip(),
        access_token=source["SAM_ACCESS_TOKEN"].strip(),
        use_ssl=_parse_bool(source.get("SAM_USE_SSL"), default=True),
    )


def run_connection_test(
    settings: SamSettings,
    *,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Authenticate to SAM and load an existing project without modifying it."""
    if connector_class is None or project_manager_class is None:
        try:
            from ansys.sam.sysml2 import (  # type: ignore[import-not-found]
                AnsysSysML2APIConnector,
                SysML2ProjectManager,
            )
        except ImportError as exc:
            raise RuntimeError(
                "PySAM SysML2 is not installed. Run: "
                "python -m pip install -r requirements.txt"
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

    return {
        "server_url": settings.server_url,
        "organization_id": settings.organization_id,
        "project_id": settings.project_id,
        "project_loaded": project is not None,
    }


def _print_success(result: Mapping[str, Any]) -> None:
    print("SAM Connection - Gate 0")
    print(f"Server ............. {result['server_url']}")
    print("Authentication ..... OK")
    print(f"Organization ....... {result['organization_id']}")
    print(f"Project ............ {result['project_id']}")
    print("Project load ....... OK")
    print()
    print("Connection test: PASSED")
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
