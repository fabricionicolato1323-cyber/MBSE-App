"""Compatibility shims for PySAM behavior required by SAM Level 1B.

PySAM 0.3.1 has a known transactional Factory inconsistency for ScriptingProject
objects: locally-created scripting attributes are stored without the underscore
prefix used by the scripting mapper. The upstream project fixed this after the
0.3.1 release (issue #152). Until a released PySAM version contains that fix,
Level 1B installs the equivalent behavior locally before creating a transaction.
"""

from __future__ import annotations

import inspect
from typing import Any
from uuid import uuid4


class PySamCompatibilityError(RuntimeError):
    """Raised when the required PySAM compatibility patch cannot be installed."""


def install_transactional_factory_fix() -> dict[str, Any]:
    """Install the upstream transactional ScriptingProject Factory fix if needed.

    Returns diagnostic metadata and performs no SAM network operation.
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

    original = Factory._create_local_element_and_stack
    if getattr(original, "_mbse_level1_transaction_fix", False):
        return {"required": True, "applied": True, "already_installed": True}

    try:
        source = inspect.getsource(original)
    except (OSError, TypeError):
        source = ""

    # The upstream fixed implementation contains this scripting-specific prefix
    # logic. Do not replace a future PySAM release that already contains it.
    if "attr_name = key" in source and 'attr_name = "_" + key' in source:
        return {"required": False, "applied": False, "already_installed": False}

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
    return {"required": True, "applied": True, "already_installed": False}
