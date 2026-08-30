from __future__ import annotations

from typing import Any

from arcadia_oa_library import ArcadiaOALibrary
from sysml_v2 import generate_sysml_v2


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def build_sysml_level1_preview(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None = None,
    drafts: list[dict[str, Any]] | None = None,
    library: ArcadiaOALibrary | None = None,
) -> dict[str, Any]:
    """Build the Level 1A textual SysML v2 projection without writing to SAM.

    Level 1 represents the complete semantic model projection. Level 1A is
    intentionally local/read-only with respect to SAM: it generates text for
    inspection and export, but performs no PySAM operation.
    """
    model = payload if isinstance(payload, dict) else {}
    nodes = _dict_rows(model.get("nodes"))
    edges = _dict_rows(model.get("edges"))
    scenario_rows = _dict_rows(
        scenarios if scenarios is not None else model.get("scenarios")
    )
    draft_rows = _dict_rows(
        drafts if drafts is not None else model.get("drafts")
    )
    valid_scenarios = [item for item in scenario_rows if item.get("valid") is not False]

    text = generate_sysml_v2(
        model,
        scenarios=scenario_rows,
        drafts=draft_rows,
        library=library,
    )
    has_confirmed_content = bool(nodes or edges or valid_scenarios)

    return {
        "level": 1,
        "phase": "A",
        "kind": "model",
        "label": "Level 1 · Model",
        "scope": "complete_model",
        "status": "ready" if has_confirmed_content else "empty",
        "text": text,
        "counts": {
            "elements": len(nodes),
            "relationships": len(edges),
            "scenarios": len(valid_scenarios),
            "temporary_items": len(draft_rows),
        },
        "sam_write_performed": False,
    }
