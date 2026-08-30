"""Reload-safe adapter for PySAM direct element creation.

PySAM 0.3.1 reloads the scripting project after each direct ``Factory.create_*``
call. The reload replaces the in-memory scripting element instances, so callers
must not reuse an element object returned by an earlier direct create as an owner
or relationship endpoint without resolving it again from the current project.

This adapter keeps the existing Factory API while rebinding every SysML element
argument by stable element ID immediately before a create call and returning the
fresh post-reload element afterwards.
"""

from __future__ import annotations

from functools import wraps
from typing import Any


class ReloadSafeReferenceError(RuntimeError):
    """Raised when a previously created SAM element cannot be rebound by ID."""


def element_id(value: Any) -> str | None:
    """Return a scripting element ID without depending on a concrete PySAM class."""
    for attr in ("id", "_id"):
        try:
            candidate = getattr(value, attr, None)
        except Exception:
            candidate = None
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return None


class ReloadSafeFactory:
    """Wrap a PySAM Factory whose direct create path reloads the project."""

    def __init__(self, project: Any, delegate: Any):
        self.project = project
        self.delegate = delegate

    def fresh(self, value: Any, *, required: bool = False) -> Any:
        """Rebind element references recursively to the project's current objects."""
        if value is None or isinstance(value, (str, bytes, int, float, bool)):
            return value
        if isinstance(value, list):
            return [self.fresh(item, required=required) for item in value]
        if isinstance(value, tuple):
            return tuple(self.fresh(item, required=required) for item in value]
        if isinstance(value, set):
            return {self.fresh(item, required=required) for item in value}
        if isinstance(value, dict):
            return {
                key: self.fresh(item, required=required)
                for key, item in value.items()
            }

        identity = element_id(value)
        if identity is None:
            return value

        finder = getattr(self.project, "find_element_by_id", None)
        current = finder(identity) if callable(finder) else None
        if current is not None:
            return current
        if required:
            raise ReloadSafeReferenceError(
                f"SAM element {identity!r} is no longer visible after the project reload."
            )
        return value

    def __getattr__(self, name: str) -> Any:
        target = getattr(self.delegate, name)
        if not name.startswith("create_") or not callable(target):
            return target

        @wraps(target)
        def reload_safe_create(*args, **kwargs):
            rebound_args = tuple(self.fresh(arg, required=True) for arg in args)
            rebound_kwargs = {
                key: self.fresh(value, required=True)
                for key, value in kwargs.items()
            }
            try:
                created = target(*rebound_args, **rebound_kwargs)
            except Exception as exc:
                raise RuntimeError(f"{name} failed: {exc}") from exc
            if created is None:
                return None
            return self.fresh(created, required=True)

        return reload_safe_create
