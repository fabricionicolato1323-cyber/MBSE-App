"""Reload-safe adapter for PySAM direct element creation.

PySAM 0.3.1 reloads a scripting project after each direct ``Factory.create_*``
call. The reload replaces the in-memory scripting element instances, so callers
must not reuse an element object returned by an earlier direct create as an owner
or relationship endpoint without resolving it again from the current project.

This adapter keeps the existing Factory API while rebinding every SysML element
argument by stable element ID immediately before a create call and returning the
fresh post-reload element afterwards.

SAM also validates some relationship payloads more strictly than the generated
PySAM metamodel classes imply. ``Subclassification`` is therefore reduced to its
native writable classifier ends. ``AllocationUsage`` connector endpoints are
derived in the SAM metamodel and cannot be populated directly; for the ArcadiaOA
SUPPORTS_CAPABILITY mapping, the transport adapter persists the same intent as a
``SatisfyRequirementUsage`` whose satisfied requirement is the Operational
Capability and whose satisfying feature is the Operational Activity.

``ConnectionUsage`` and ``FlowConnectionUsage`` also expose derived endpoint
collections (Relationship.source/target, Connector.target_feature and
Connector.related_feature). The adapter therefore creates the connector itself
without those derived attributes and then represents each binary endpoint as an
owned end ``ReferenceUsage`` with an owned ``ReferenceSubsetting`` to the actual
model feature. This mirrors the SysML v2 abstract syntax behind ``connect A to B``
without trying to mutate derived ELists.

The Level 1A textual model remains the normative translation artifact.
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


def _first(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _normalize_create_call(
    name: str,
    kwargs: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Return the server-valid Factory method and payload for a simple create call."""
    normalized = dict(kwargs)

    if name == "create_subclassification":
        # SysML v2 Subclassification owns the semantic classifier ends directly.
        # Relationship.source/target are inherited/redefined projections and SAM
        # rejects a direct-create payload that redundantly submits them alongside
        # subclassifier/superclassifier.
        normalized.pop("source", None)
        normalized.pop("target", None)
        return name, normalized

    if name == "create_allocation_usage":
        # ArcadiaOA SUPPORTS_CAPABILITY is emitted textually as:
        #     allocate <capability> to <activity>;
        # In the SAM metamodel, AllocationUsage inherits Connector endpoint views
        # whose source/target/relatedFeature collections are derived and immutable.
        # OperationalCapability is already a RequirementUsage, so the equivalent
        # native SAM relation is SatisfyRequirementUsage(capability, activity).
        satisfied_requirement = normalized.get("source_feature") or _first(
            normalized.get("source")
        )
        satisfying_feature = _first(normalized.get("target_feature")) or _first(
            normalized.get("target")
        )
        if satisfied_requirement is None or satisfying_feature is None:
            raise ReloadSafeReferenceError(
                "Capability-support transport requires both an Operational Capability "
                "and an Operational Activity."
            )
        transport_kwargs = {
            "name": normalized.get("name"),
            "owner": normalized.get("owner"),
            "satisfied_requirement": satisfied_requirement,
            "satisfying_feature": satisfying_feature,
        }
        return (
            "create_satisfy_requirement_usage",
            {key: value for key, value in transport_kwargs.items() if value is not None},
        )

    return name, normalized


class ReloadSafeFactory:
    """Wrap a PySAM Factory whose direct create path reloads the project."""

    _CONNECTOR_METHODS = {"create_connection_usage", "create_flow_connection_usage"}
    _DERIVED_CONNECTOR_KEYS = {
        "source",
        "target",
        "source_feature",
        "target_feature",
        "related_feature",
        "connector_end",
    }

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
            return tuple(self.fresh(item, required=required) for item in value)
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

    def _direct_create(
        self,
        method_name: str,
        *,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        label: str | None = None,
    ) -> Any:
        """Call one delegate create method with fresh references and rebind its result."""
        target = getattr(self.delegate, method_name)
        rebound_args = tuple(self.fresh(arg, required=True) for arg in args)
        rebound_kwargs = {
            key: self.fresh(value, required=True)
            for key, value in (kwargs or {}).items()
        }
        try:
            created = target(*rebound_args, **rebound_kwargs)
        except Exception as exc:
            raise RuntimeError(f"{label or method_name} failed: {exc}") from exc
        if created is None:
            return None
        return self.fresh(created, required=True)

    def _create_binary_connector(
        self,
        method_name: str,
        *,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Create a binary connector using writable owned reference ends."""
        if args:
            raise ReloadSafeReferenceError(
                f"{method_name} connector transport requires keyword arguments."
            )

        raw = dict(kwargs)
        source = raw.get("source_feature") or _first(raw.get("source"))
        target = _first(raw.get("target_feature")) or _first(raw.get("target"))
        if source is None or target is None:
            raise ReloadSafeReferenceError(
                f"{method_name} requires both source and target features."
            )

        base_kwargs = {
            key: value
            for key, value in raw.items()
            if key not in self._DERIVED_CONNECTOR_KEYS
        }
        connector = self._direct_create(
            method_name,
            kwargs=base_kwargs,
            label=method_name,
        )

        base_name = str(raw.get("name") or "connector").strip() or "connector"
        for role, endpoint in (("source", source), ("target", target)):
            end = self._direct_create(
                "create_reference_usage",
                kwargs={
                    "name": f"{base_name}__{role}_end",
                    "owner": connector,
                    "is_end": True,
                },
                label=f"{method_name} {role} end",
            )
            self._direct_create(
                "create_reference_subsetting",
                kwargs={
                    "owner": end,
                    "referencing_feature": end,
                    "referenced_feature": endpoint,
                },
                label=f"{method_name} {role} reference subsetting",
            )

        return self.fresh(connector, required=True)

    def __getattr__(self, name: str) -> Any:
        original_target = getattr(self.delegate, name)
        if not name.startswith("create_") or not callable(original_target):
            return original_target

        @wraps(original_target)
        def reload_safe_create(*args, **kwargs):
            if name in self._CONNECTOR_METHODS:
                return self._create_binary_connector(
                    name,
                    args=args,
                    kwargs=kwargs,
                )

            transport_name, normalized_kwargs = _normalize_create_call(name, kwargs)
            if transport_name == name:
                label = name
            else:
                label = f"{name} via {transport_name}"
            return self._direct_create(
                transport_name,
                args=args,
                kwargs=normalized_kwargs,
                label=label,
            )

        return reload_safe_create
