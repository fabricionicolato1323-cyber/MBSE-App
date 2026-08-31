from __future__ import annotations

from typing import Any

import change_impact_refinement as _impact


def _rename_selected(self: Any, node_id: str, friendly_kind: str) -> None:
    old_name = self.model.name(node_id)
    node_type = str(self.model.graph.nodes[node_id].get("type") or "")
    new_name = self.ask_validated(
        f"What should '{old_name}' be called?",
        (
            f"Enter the proposed new name for this existing {friendly_kind}. The stable "
            "model ID and all existing relationships will be preserved."
        ),
        expected_concept=node_type,
        why=(
            "The app previews the proposed rename first. The changed item is red and "
            "directly affected items are orange before you decide whether to commit it."
        ),
    )

    ok, error, preview = _impact.preview_rename_model_node(self.model, node_id, new_name)
    if not ok:
        self.add_notice(f"Rename preview was not created: {error}")
        return

    impacted = _impact._impact_names(preview)
    impact_text = ", ".join(impacted) if impacted else "none"
    self.add_notice(
        f"Rename impact preview: '{old_name}' → '{new_name}'. Proposed change: red. "
        f"Directly affected items: {impact_text}. Affected items: orange."
    )
    if not self.ask_yes_no(
        f"Rename {friendly_kind} '{old_name}' to '{new_name}'?",
        (
            "Review the red/orange preview first. Yes commits the rename using the same "
            "stable ID; no leaves the semantic model unchanged."
        ),
    ):
        _impact.clear_change_presentation(self.model)
        self.add_notice("Rename cancelled. Nothing was changed.")
        return

    ok, error, presentation = _impact.rename_model_node(self.model, node_id, new_name)
    if not ok:
        _impact.clear_change_presentation(self.model)
        self.add_notice(f"Rename was not applied: {error}")
        return

    propagated = int(presentation.get("propagated_name_copies") or 0)
    # Change colours are an impact-review state only. Once the user confirms the
    # semantic mutation, return every projection to its normal OA presentation.
    _impact.clear_change_presentation(self.model)
    suffix = (
        f" Updated {propagated} redundant display-name reference(s) linked by ID."
        if propagated
        else " All semantic references continue to resolve by stable ID."
    )
    self.add_notice(
        f"Renamed '{old_name}' to '{new_name}'. The impact preview is complete and the "
        f"model display has returned to its normal colours.{suffix}"
    )


def _delete_selected(self: Any, node_id: str, friendly_kind: str) -> None:
    name = self.model.name(node_id)
    presentation = _impact.preview_delete_model_node(self.model, node_id)
    impacted = _impact._impact_names(presentation)
    impact_text = ", ".join(impacted) if impacted else "none"
    self.add_notice(
        f"Delete impact preview for '{name}'. Target: red. "
        f"Directly affected items: {impact_text}. Affected items: orange."
    )
    if not self.ask_yes_no(
        f"Delete {friendly_kind} '{name}'?",
        (
            "Deleting removes the element and all relationships incident on it. "
            "Review the red/orange impact preview before confirming."
        ),
    ):
        _impact.clear_change_presentation(self.model)
        self.add_notice("Delete cancelled. Nothing was removed.")
        return

    ok, error, _presentation = _impact.delete_model_node(self.model, node_id)
    if not ok:
        _impact.clear_change_presentation(self.model)
        self.add_notice(f"Delete was not applied: {error}")
        return
    _impact.clear_change_presentation(self.model)
    self.add_notice(
        f"Deleted {friendly_kind} '{name}'. The impact preview is complete and the "
        "remaining model display has returned to its normal colours."
    )


def install_change_impact_finalize_support() -> None:
    """Make impact colours preview-only for both rename and delete."""
    # The previously installed refinement handlers resolve these module globals
    # at call time, so replacing them updates both action and participant flows
    # without duplicating the surrounding choice menus.
    _impact._rename_selected = _rename_selected
    _impact._delete_selected = _delete_selected
