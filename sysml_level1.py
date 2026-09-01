from __future__ import annotations

from typing import Any

from sam_full_projection import generate_sam_sysml_v2 as generate_sysml_v2
from sam_reference_profile import SAMReferenceProfile
from sam_level1_sync import level1_snapshot_digest


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def build_sysml_level1_preview(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None = None,
    drafts: list[dict[str, Any]] | None = None,
    library: SAMReferenceProfile | None = None,
) -> dict[str, Any]:
    """Build the SAM-compatible Level 1A SysML v2 projection without writing to SAM.

    Level 1A and the managed SAM baseline deliberately use the same SAM reference
    profile and projection rules, so the text reviewed by the user has the same
    ownership, package, exchange, allocation, and scenario structure as the PySAM
    baseline. The ``library`` parameter name is retained for API compatibility;
    it now accepts the declarative ``SAMReferenceProfile`` used by SAM projection.
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
        profile=library,
    )
    has_confirmed_content = bool(nodes or edges or valid_scenarios)

    return {
        "level": 1,
        "phase": "A",
        "kind": "model",
        "label": "Level 1 · Model",
        "scope": "complete_model",
        "status": "ready" if has_confirmed_content else "empty",
        "snapshot_digest": level1_snapshot_digest(model, valid_scenarios),
        "text": text,
        "counts": {
            "elements": len(nodes),
            "relationships": len(edges),
            "scenarios": len(valid_scenarios),
            "temporary_items": len(draft_rows),
        },
        "sam_write_performed": False,
    }
