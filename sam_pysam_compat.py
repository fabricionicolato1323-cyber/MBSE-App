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

The live SAM/PySAM combination can also reload a ``ReferenceUsage`` outside the
owner traversal used by the scripting project, even though the relationship is
still present in the project. LOCATED_IN uses that SysML shape. The adoption shim
therefore falls back to a project-wide relationship-name lookup and resolves
``referencedFeature`` through owned ``ReferenceSubsetting`` elements when needed.
Direct creation of a LOCATED_IN reference is likewise normalized to a writable
ReferenceUsage + ReferenceSubsetting pair instead of submitting the derived
``referencedFeature`` projection on the ReferenceUsage itself.
"""

from __future__ import annotations

import inspect
import sys
from contextvars import ContextVar
from functools import wraps
from typing import Any
from uuid import uuid4


class PySamCompatibilityError(RuntimeError):
    """Raised when the required PySAM compatibility patch cannot be installed."""


def install_relationship_reload_aliases() -> dict[str, Any]:
    """Teach the Level 1 read-only matcher SAM's reload-specific relationship shapes.

    This performs no SAM network operation and does not change any write payload.
    It augments relationship adoption so SUPPORTS_CAPABILITY can be read through
    native satisfy fields and LOCATED_IN can be found even when PySAM omits the
    reloaded ReferenceUsage from the package-owner traversal.
    """
    try:
        import sam_level1_complete_incremental as complete
    except ImportError:
        return {"required": True, "applied": False, "available": False}

    context = getattr(complete, "_mbse_relationship_adoption_project_context", None)
    if not isinstance(context, ContextVar):
        context = ContextVar("mbse_relationship_adoption_project", default=None)
        complete._mbse_relationship_adoption_project_context = context

    load_result: dict[str, Any]
    current_load = getattr(complete, "_load_project", None)
    if not callable(current_load):
        load_result = {"required": True, "applied": False, "available": False}
    elif getattr(current_load, "_mbse_relationship_project_context_fix", False):
        load_result = {"required": True, "applied": True, "already_installed": True}
    else:

        @wraps(current_load)
        def load_project_with_adoption_context(*args, **kwargs):
            result = current_load(*args, **kwargs)
            if isinstance(result, tuple) and len(result) >= 3:
                context.set(result[2])
            return result

        load_project_with_adoption_context._mbse_relationship_project_context_fix = True
        complete._load_project = load_project_with_adoption_context
        load_result = {"required": True, "applied": True, "already_installed": False}

    refs_result: dict[str, Any]
    original_refs = getattr(complete, "_mapped_refs", None)
    if not callable(original_refs):
        refs_result = {"required": True, "applied": False, "available": False}
    elif getattr(original_refs, "_mbse_relationship_reload_fix", False):
        refs_result = {"required": True, "applied": True, "already_installed": True}
    else:

        def mapped_refs(element: Any, *attrs: str) -> list[Any]:
            values = list(original_refs(element, *attrs))
            requested = set(attrs)
            if requested.intersection({"source", "_source"}):
                values.extend(
                    original_refs(
                        element,
                        "satisfied_requirement",
                        "_satisfied_requirement",
                        "satisfiedRequirement",
                        "_satisfiedRequirement",
                    )
                )
            if requested.intersection({"target", "_target"}):
                values.extend(
                    original_refs(
                        element,
                        "satisfying_feature",
                        "_satisfying_feature",
                        "satisfyingFeature",
                        "_satisfyingFeature",
                    )
                )

            reference_attrs = {
                "referenced_feature",
                "_referenced_feature",
                "referencedFeature",
                "_referencedFeature",
            }
            if requested.intersection(reference_attrs):
                project = context.get()
                descendants = getattr(complete, "_descendants", None)
                if project is not None and callable(descendants):
                    try:
                        children = descendants(project, element)
                    except Exception:
                        children = []
                    for child in children:
                        values.extend(original_refs(child, *tuple(reference_attrs)))
            return values

        mapped_refs._mbse_relationship_reload_fix = True
        mapped_refs._mbse_supports_capability_reload_fix = True
        mapped_refs._mbse_located_in_reference_subsetting_fix = True
        complete._mapped_refs = mapped_refs
        refs_result = {"required": True, "applied": True, "already_installed": False}

    match_result: dict[str, Any]
    original_match = getattr(complete, "_match_existing", None)
    if not callable(original_match):
        match_result = {"required": True, "applied": False, "available": False}
    elif getattr(original_match, "_mbse_project_wide_relationship_adoption_fix", False):
        match_result = {"required": True, "applied": True, "already_installed": True}
    else:

        @wraps(original_match)
        def match_existing(descendants: list[Any], edge: dict[str, Any], node_ids: dict[str, str]):
            matched = original_match(descendants, edge, node_ids)
            if matched is not None:
                return matched

            project = context.get()
            finder = getattr(project, "find_elements_by_name", None) if project is not None else None
            relationship_name = getattr(complete, "_relationship_name", None)
            if not callable(finder) or not callable(relationship_name):
                return None

            try:
                candidates = list(finder(relationship_name(edge)) or [])
            except Exception:
                candidates = []
            if not candidates:
                return None

            # Reuse the normal semantic matcher on the project-wide candidates.
            # The patched _mapped_refs above can resolve a LOCATED_IN target via an
            # owned ReferenceSubsetting, so same-name relationships remain
            # distinguishable whenever SAM preserved their semantic endpoints.
            return original_match(candidates, edge, node_ids)

        match_existing._mbse_project_wide_relationship_adoption_fix = True
        complete._match_existing = match_existing
        match_result = {"required": True, "applied": True, "already_installed": False}

    required = True
    applied = any(
        result.get("applied") for result in (load_result, refs_result, match_result)
    )
    already_installed = all(
        result.get("already_installed") for result in (load_result, refs_result, match_result)
    )
    return {
        "required": required,
        "applied": applied,
        "already_installed": already_installed,
        "project_context": load_result,
        "aliases": refs_result,
        "project_wide_adoption": match_result,
    }


def _install_reference_usage_subsetting_policy() -> dict[str, Any]:
    """Persist LOCATED_IN using writable ReferenceUsage/ReferenceSubsetting fields.

    SAM treats ``ReferenceUsage.referencedFeature`` as a derived projection in the
    live PoC environment. Submitting it directly can create a relationship whose
    semantic target is not recoverable after a fresh reload. Build the reference
    usage first, then create owned ReferenceSubsetting element(s) that point to the
    referenced model feature. Connector-end ReferenceUsages, which do not submit a
    referenced_feature argument, are unchanged.
    """
    try:
        from sam_reload_safe_factory import ReloadSafeFactory
    except ImportError:
        return {"required": True, "applied": False, "available": False}

    original_getattr = ReloadSafeFactory.__getattr__
    if getattr(original_getattr, "_mbse_reference_usage_subsetting_fix", False):
        return {"required": True, "applied": True, "already_installed": True}

    @wraps(original_getattr)
    def reference_safe_getattr(self, name: str):
        target = original_getattr(self, name)
        if name != "create_reference_usage" or not callable(target):
            return target

        @wraps(target)
        def create_reference_usage(*args, **kwargs):
            referenced_value = kwargs.get("referenced_feature")
            if referenced_value is None:
                return target(*args, **kwargs)
            if args:
                # Current MBSE-App writers use keyword-only reference creation.
                # Preserve the delegate behavior rather than guessing positional
                # argument semantics for an external caller.
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
            create_subsetting = original_getattr(self, "create_reference_subsetting")
            for referenced_feature in referenced:
                create_subsetting(
                    owner=usage,
                    referencing_feature=usage,
                    referenced_feature=referenced_feature,
                )
            return self.fresh(usage, required=True)

        create_reference_usage._mbse_reference_usage_subsetting_fix = True
        return create_reference_usage

    reference_safe_getattr._mbse_reference_usage_subsetting_fix = True
    ReloadSafeFactory.__getattr__ = reference_safe_getattr
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
    transactional field names, reload-safe relationship adoption, writable
    LOCATED_IN reference semantics, and the semantic-only annotation policy used
    by the PoC transport.
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

    relationship_result = install_relationship_reload_aliases()
    reference_result = _install_reference_usage_subsetting_policy()
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

    results = (
        factory_result,
        observer_result,
        metadata_result,
        relationship_result,
        reference_result,
    )
    required = any(bool(result.get("required")) for result in results)
    applied = any(bool(result.get("applied")) for result in results)
    already_installed = bool(
        required
        and all(
            not result.get("required") or result.get("already_installed")
            for result in results
        )
    )
    return {
        "required": required,
        "applied": applied,
        "already_installed": already_installed,
        "factory": factory_result,
        "observer": observer_result,
        "metadata": metadata_result,
        "relationships": relationship_result,
        "reference_usage": reference_result,
    }


# web_app imports this module during startup after the Level 1 dispatcher, so the
# matcher is already available and can be patched before any SAM preview/send.
install_relationship_reload_aliases()
