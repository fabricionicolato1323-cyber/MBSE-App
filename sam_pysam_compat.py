"""Compatibility shims for PySAM behavior required by SAM Level 1B.

PySAM 0.3.1 has two related transactional inconsistencies for ScriptingProject
objects. Locally-created scripting attributes must use the underscore-prefixed
storage used by the scripting mapper, while transaction commits must serialize
those internal names back to canonical SysML JSON field names. The released
0.3.1 Factory misses the former behavior and its ModificationObserver misses the
latter. Until a released PySAM version contains both fixes, Level 1B installs the
equivalent behavior locally before creating a transaction.

SAM also reloads ``SatisfyRequirementUsage`` using its native semantic fields
(``satisfiedRequirement`` / ``satisfyingFeature``), while the Companion App's
ArcadiaOA contract describes SUPPORTS_CAPABILITY as an allocation with
``source`` / ``target`` endpoints. The read-only alias shim below makes those
representations equivalent only while matching an existing relationship.
"""

from __future__ import annotations

import inspect
import sys
from typing import Any
from uuid import uuid4


class PySamCompatibilityError(RuntimeError):
    """Raised when the required PySAM compatibility patch cannot be installed."""


def install_relationship_reload_aliases() -> dict[str, Any]:
    """Teach the Level 1 read-only matcher SAM's native satisfy field names.

    This performs no SAM network operation and does not change any write payload.
    It only augments the helper used when adopting already-created relationships
    after a fresh PySAM/SAM reload.
    """
    try:
        import sam_level1_complete_incremental as complete
    except ImportError:
        return {"required": True, "applied": False, "available": False}

    original = getattr(complete, "_mapped_refs", None)
    if not callable(original):
        return {"required": True, "applied": False, "available": False}
    if getattr(original, "_mbse_supports_capability_reload_fix", False):
        return {"required": True, "applied": True, "already_installed": True}

    def mapped_refs(element: Any, *attrs: str) -> list[Any]:
        values = list(original(element, *attrs))
        requested = set(attrs)
        if requested.intersection({"source", "_source"}):
            values.extend(
                original(
                    element,
                    "satisfied_requirement",
                    "_satisfied_requirement",
                    "satisfiedRequirement",
                    "_satisfiedRequirement",
                )
            )
        if requested.intersection({"target", "_target"}):
            values.extend(
                original(
                    element,
                    "satisfying_feature",
                    "_satisfying_feature",
                    "satisfyingFeature",
                    "_satisfyingFeature",
                )
            )
        return values

    mapped_refs._mbse_supports_capability_reload_fix = True
    complete._mapped_refs = mapped_refs
    return {"required": True, "applied": True, "already_installed": False}


def _install_semantic_only_annotation_policy() -> dict[str, Any]:
    """Skip optional SAM annotation elements during synchronization.

    The live PoC previously created one ``Comment`` for many source nodes,
    relationships, and scenario steps. In direct-create mode every annotation is
    another SAM commit followed by a complete project reload, so optional
    metadata can dominate the elapsed transfer time. The semantic SysML model is
    already represented by native SAM elements and the local Level 1 text/model,
    therefore the transport now omits these optional annotations.

    Patch both the defining helper and any already-imported aliases. Modules
    imported later will naturally receive the patched helper from
    ``sam_level1_sync``.
    """
    try:
        import sam_level1_sync as sync
    except ImportError:
        return {"required": True, "applied": False, "available": False}

    current = getattr(sync, "_documentation", None)
    if not callable(current):
        return {"required": True, "applied": False, "available": False}
    if getattr(current, "_mbse_semantic_only_sam_metadata", False):
        return {"required": True, "applied": True, "already_installed": True}

    def skip_optional_documentation(*args, **kwargs):
        return None

    skip_optional_documentation._mbse_semantic_only_sam_metadata = True
    sync._documentation = skip_optional_documentation

    # These modules import _documentation by value. Update aliases that already
    # exist in the current process so the policy applies to the same send call.
    for module_name in (
        "sam_level1_direct",
        "sam_level1_managed_direct",
        "sam_level1_incremental",
        "sam_level1_communication_incremental",
        "sam_level1_scenario_incremental",
        "sam_level1_complete_incremental",
    ):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "_documentation"):
            setattr(module, "_documentation", skip_optional_documentation)

    return {"required": True, "applied": True, "already_installed": False}


def _install_transactional_observer_field_fix() -> dict[str, Any]:
    """Normalize scripting storage names before a transactional commit.

    ``SysMLElement`` stores scripting-layer attributes as ``_name``, ``_owner``,
    ``_action_definition``, and similar names. Non-transactional observer writes
    remove the leading underscore before building a ``DataVersion``; PySAM 0.3.1
    does not do that in ``_commit_stack``. Without this shim the serializer emits
    ``Name``/``Owner``/``ActionDefinition`` instead of the canonical
    ``name``/``owner``/``actionDefinition`` fields, so SAM can create the element
    type while losing its name, ownership, or semantic references after reload.

    The live SAM used by the PoC also rejects ``Documentation`` creation. Direct
    writes can detect that immediately and fall back to ``Comment``, but an atomic
    transaction cannot discover the rejection until the whole stack is committed.
    Documentation is optional metadata, so transactional commits drop only those
    DataVersions rather than allowing them to abort semantic scenario creation.
    """
    try:
        from ansys.sam.sysml2.dto.commit.commit_class import Commit
        from ansys.sam.sysml2.dto.commit.data_version import DataVersion
        from ansys.sam.sysml2.observer.observer import ModificationObserver
    except ImportError as exc:  # pragma: no cover - optional dependency boundary.
        raise PySamCompatibilityError(
            "PySAM SysML2 is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc

    original = ModificationObserver._commit_stack
    if getattr(original, "_mbse_level1_transaction_field_fix", False):
        return {"required": True, "applied": True, "already_installed": True}

    try:
        source = inspect.getsource(original)
    except (OSError, TypeError):
        source = ""

    upstream_normalizes = (
        'startswith("_")' in source
        and "change.add_change" in source
        and ("field_name" in source or "name =" in source)
    )
    if upstream_normalizes:
        return {"required": False, "applied": False, "already_installed": False}

    def fixed_commit_stack(self):
        commit = Commit(self._project_id)
        for key, changes in self._stack.items():
            element_type = next(
                (
                    field_value
                    for field_name, field_value in changes
                    if field_name == "@type"
                ),
                None,
            )
            if element_type == "Documentation":
                continue

            change = DataVersion()
            if not key.startswith("value:"):
                change.identify(key)
            for field_name, field_value in changes:
                if field_name.startswith("_"):
                    field_name = field_name[1:]
                change.add_change(field_name, field_value)
            commit.add_change(change)
        if len(commit.changes) > 0:
            self._connector.create_commit(self._project_id, commit.to_json())
            self.reload_project()

    fixed_commit_stack._mbse_level1_transaction_field_fix = True
    ModificationObserver._commit_stack = fixed_commit_stack
    return {"required": True, "applied": True, "already_installed": False}


def install_transactional_factory_fix() -> dict[str, Any]:
    """Install the PySAM transactional ScriptingProject compatibility fixes.

    Returns diagnostic metadata and performs no SAM network operation. The
    compatibility layer covers local scripting attribute storage, canonical
    transactional field names, and the semantic-only annotation policy used by
    the PoC transport.
    """
    try:
        from ansys.sam.sysml2.classes.project import Project
        from ansys.sam.sysml2.classes.sysml_element import SysMLElement
        from ansys.sam.sysml2.data_structures.observed_list import ObservedList
        from ansys.sam.sysml2.tools import Factory
    except ImportError as exc:  # pragma: no cover - optional dependency boundary.
        raise PySamCompatibilityError(
            "PySAM SysML2 is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc

    metadata_result = _install_semantic_only_annotation_policy()
    observer_result = _install_transactional_observer_field_fix()

    original = Factory._create_local_element_and_stack
    if getattr(original, "_mbse_level1_transaction_fix", False):
        factory_result = {
            "required": True,
            "applied": True,
            "already_installed": True,
        }
    else:
        try:
            source = inspect.getsource(original)
        except (OSError, TypeError):
            source = ""

        upstream_factory_fixed = (
            "attr_name = key" in source and 'attr_name = "_" + key' in source
        )
        if upstream_factory_fixed:
            factory_result = {
                "required": False,
                "applied": False,
                "already_installed": False,
            }
        else:

            def fixed_create_local_element_and_stack(self, element_type: str, **kwargs):
                from ansys.sam.sysml2.builder.classes.sysml_util import SysMLUtil

                element_id = str(uuid4())
                is_scripting = not isinstance(self._project, Project)
                if not is_scripting:
                    constructor = SysMLUtil.get_sysml_constructor(element_type)
                    instance = constructor(element_id)
                else:
                    instance = SysMLElement(element_id)
                    instance.__class__ = type(element_type, (SysMLElement,), {})

                instance._observer = self._project.get_root_package()._observer
                instance._observer.notify(element_id, "@type", element_type)
                for key, value in kwargs.items():
                    attr_name = key
                    if is_scripting and not key.startswith("_"):
                        attr_name = "_" + key
                    if isinstance(value, list):
                        if not hasattr(instance, attr_name):
                            setattr(
                                instance,
                                attr_name,
                                ObservedList(owner=instance, name=attr_name),
                            )
                        getattr(instance, attr_name).extend(value)
                    else:
                        setattr(instance, attr_name, value)
                self._project.add_element(instance)
                return instance

            fixed_create_local_element_and_stack._mbse_level1_transaction_fix = True
            Factory._create_local_element_and_stack = fixed_create_local_element_and_stack
            factory_result = {
                "required": True,
                "applied": True,
                "already_installed": False,
            }

    required = bool(
        factory_result["required"]
        or observer_result["required"]
        or metadata_result["required"]
    )
    applied = bool(
        factory_result["applied"]
        or observer_result["applied"]
        or metadata_result["applied"]
    )
    already_installed = bool(
        required
        and (not factory_result["required"] or factory_result.get("already_installed"))
        and (not observer_result["required"] or observer_result.get("already_installed"))
        and (not metadata_result["required"] or metadata_result.get("already_installed"))
    )
    return {
        "required": required,
        "applied": applied,
        "already_installed": already_installed,
        "factory": factory_result,
        "observer": observer_result,
        "metadata": metadata_result,
    }


# web_app imports this module during startup after the Level 1 dispatcher, so the
# matcher is already available and can be patched before any SAM preview/send.
install_relationship_reload_aliases()
