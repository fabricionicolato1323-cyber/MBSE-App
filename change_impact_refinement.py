from __future__ import annotations

from typing import Any

from focused_refinement import FocusedRefinementMixin


PRESENTATION_KEY = "_revision_presentation"


def _clean_name(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _node_info(model: Any, node_id: str, *, fallback_name: str = "") -> dict[str, str]:
    data = model.graph.nodes.get(node_id, {}) if node_id in model.graph else {}
    return {
        "id": str(node_id),
        "name": _clean_name(data.get("name") or fallback_name or node_id),
        "type": str(data.get("type") or ""),
    }


def directly_impacted_node_ids(model: Any, node_id: str) -> list[str]:
    """Return the directly dependent model elements around one changed node.

    The graph stores semantic references by stable ID. For a rename, the changed
    element itself is the write target while immediate graph neighbours are the
    elements whose rendered references/relationships can visibly change. Keeping
    this first propagation step explicit avoids falsely claiming transitive impact
    where no semantic dependency has been established.
    """
    if node_id not in model.graph:
        return []
    impacted: set[str] = set()
    for source, target, _data in model.graph.in_edges(node_id, data=True):
        if source != node_id:
            impacted.add(str(source))
        if target != node_id:
            impacted.add(str(target))
    for source, target, _data in model.graph.out_edges(node_id, data=True):
        if source != node_id:
            impacted.add(str(source))
        if target != node_id:
            impacted.add(str(target))
    return sorted(impacted)


def _persist_if_web_model(model: Any) -> None:
    persist = getattr(model, "_persist", None)
    if callable(persist):
        persist()


def set_change_presentation(
    model: Any,
    *,
    operation: str,
    modified: list[dict[str, str]],
    impacted_ids: list[str],
) -> dict[str, Any]:
    impacted = [
        _node_info(model, node_id)
        for node_id in impacted_ids
        if node_id in model.graph
    ]
    presentation = {
        "operation": str(operation),
        "modified": list(modified),
        "impacted": impacted,
        "modified_ids": [item["id"] for item in modified],
        "impacted_ids": [item["id"] for item in impacted],
    }
    model.graph.graph[PRESENTATION_KEY] = presentation
    _persist_if_web_model(model)
    return presentation


def clear_change_presentation(model: Any) -> None:
    if PRESENTATION_KEY in model.graph.graph:
        model.graph.graph.pop(PRESENTATION_KEY, None)
        _persist_if_web_model(model)


def _duplicate_for_name(model: Any, node_id: str, name: str) -> str | None:
    node_type = str(model.graph.nodes[node_id].get("type") or "")
    if node_type in {"OperationalActor", "OperationalEntity"}:
        duplicate = model.find_participant_duplicate(name)
    else:
        duplicate = model.find_duplicate(node_type, name)
    if duplicate == node_id:
        return None
    return duplicate


def rename_model_node(model: Any, node_id: str, new_name: str) -> tuple[bool, str, dict[str, Any]]:
    if node_id not in model.graph:
        return False, "The selected model element no longer exists.", {}

    normalized = _clean_name(new_name)
    if not normalized:
        return False, "The new name cannot be empty.", {}
    current = _clean_name(model.graph.nodes[node_id].get("name") or node_id)
    if normalized.casefold() == current.casefold():
        return False, "The new name is the same as the current name.", {}
    duplicate = _duplicate_for_name(model, node_id, normalized)
    if duplicate:
        return False, f"'{normalized}' is already used by another compatible model element.", {}

    impacted_ids = directly_impacted_node_ids(model, node_id)
    if not model.update_node_attributes(node_id, name=normalized):
        return False, "The selected model element could not be renamed.", {}

    presentation = set_change_presentation(
        model,
        operation="rename",
        modified=[_node_info(model, node_id)],
        impacted_ids=impacted_ids,
    )
    return True, "", presentation


def preview_delete_model_node(model: Any, node_id: str) -> dict[str, Any]:
    if node_id not in model.graph:
        return {}
    impacted_ids = directly_impacted_node_ids(model, node_id)
    return set_change_presentation(
        model,
        operation="delete_preview",
        modified=[_node_info(model, node_id)],
        impacted_ids=impacted_ids,
    )


def delete_model_node(model: Any, node_id: str) -> tuple[bool, str, dict[str, Any]]:
    if node_id not in model.graph:
        return False, "The selected model element no longer exists.", {}

    deleted = _node_info(model, node_id)
    impacted_ids = directly_impacted_node_ids(model, node_id)
    impacted_before = [
        _node_info(model, impacted_id)
        for impacted_id in impacted_ids
        if impacted_id in model.graph
    ]

    checkpoint = getattr(model, "_checkpoint", None)
    if callable(checkpoint):
        checkpoint()
    model.graph.remove_node(node_id)

    presentation = {
        "operation": "delete",
        "modified": [deleted],
        "impacted": impacted_before,
        "modified_ids": [deleted["id"]],
        "impacted_ids": [item["id"] for item in impacted_before],
    }
    model.graph.graph[PRESENTATION_KEY] = presentation
    _persist_if_web_model(model)
    return True, "", presentation


def _impact_names(presentation: dict[str, Any]) -> list[str]:
    return [
        _clean_name(item.get("name"))
        for item in presentation.get("impacted", [])
        if isinstance(item, dict) and _clean_name(item.get("name"))
    ]


def _rename_selected(self: Any, node_id: str, friendly_kind: str) -> None:
    old_name = self.model.name(node_id)
    node_type = str(self.model.graph.nodes[node_id].get("type") or "")
    new_name = self.ask_validated(
        f"What should '{old_name}' be called?",
        (
            f"Enter the new name for this existing {friendly_kind}. The stable model ID "
            "and all existing relationships will be preserved."
        ),
        expected_concept=node_type,
        why=(
            "Renaming changes the label of the same model element. The app highlights "
            "the changed element in red and directly impacted references in orange."
        ),
    )
    ok, error, presentation = rename_model_node(self.model, node_id, new_name)
    if not ok:
        self.add_notice(f"Rename was not applied: {error}")
        return

    impacted = _impact_names(presentation)
    impact_text = ", ".join(impacted) if impacted else "none"
    self.add_notice(
        f"Renamed '{old_name}' to '{new_name}'. Changed element: red. "
        f"Directly impacted model elements: {impact_text}. Impacted elements: orange."
    )


def _delete_selected(self: Any, node_id: str, friendly_kind: str) -> None:
    name = self.model.name(node_id)
    presentation = preview_delete_model_node(self.model, node_id)
    impacted = _impact_names(presentation)
    impact_text = ", ".join(impacted) if impacted else "none"
    self.add_notice(
        f"Delete impact preview for '{name}'. Target: red. "
        f"Directly impacted model elements: {impact_text}. Impacted elements: orange."
    )
    if not self.ask_yes_no(
        f"Delete {friendly_kind} '{name}'?",
        (
            "Deleting removes the element and all relationships incident on it. "
            "Review the red/orange impact preview before confirming."
        ),
    ):
        clear_change_presentation(self.model)
        self.add_notice("Delete cancelled. Nothing was removed.")
        return

    ok, error, _presentation = delete_model_node(self.model, node_id)
    if not ok:
        self.add_notice(f"Delete was not applied: {error}")
        return
    self.add_notice(
        f"Deleted {friendly_kind} '{name}'. Directly impacted remaining elements stay orange for review."
    )


def _refine_selected_action_with_edit(self: Any, action_id: str) -> None:
    action_label = self.model.action_label(action_id)
    choice = self.ask_choice(
        f"What would you like to refine for '{action_label}'?",
        [
            ("rename", "Rename this action"),
            ("delete", "Delete this action"),
            ("interactions", "Interactions from this action"),
            ("characteristics", "Characteristics / limits for this action"),
            ("related_action", "Add another action for the same participant"),
            ("back", "Back to the next-step menu"),
        ],
        "Edit or refine one aspect of the selected action without changing unrelated model items.",
    )

    if choice == "rename":
        _rename_selected(self, action_id, "action")
    elif choice == "delete":
        _delete_selected(self, action_id, "action")
    elif choice == "interactions":
        self._refine_interactions_from_source(action_id)
    elif choice == "characteristics":
        self._capture_characteristics_for_action(action_id)
    elif choice == "related_action":
        self._add_action_for_same_performer(action_id)


def _refine_selected_participant_with_edit(self: Any, participant_id: str) -> None:
    while participant_id in self.model.graph:
        participant_name = self.model.name(participant_id)
        choice = self.ask_choice(
            f"What would you like to refine for '{participant_name}'?",
            [
                ("rename", "Rename this participant / context element"),
                ("delete", "Delete this participant / context element"),
                ("actions", "Actions performed by this participant"),
                ("location", "Location / operational area"),
                ("structure", "Structural membership / larger element"),
                ("back", "Back to the next-step menu"),
            ],
            (
                "Edit the selected element or refine its behavior, location, or structural "
                "membership. Rename preserves the stable model ID."
            ),
        )

        if choice == "back":
            return
        if choice == "rename":
            _rename_selected(self, participant_id, "participant / context element")
            continue
        if choice == "delete":
            _delete_selected(self, participant_id, "participant / context element")
            return
        if choice == "actions":
            self.capture_actions_for_participant(participant_id)
            continue
        if choice == "location":
            self._refine_participant_location(participant_id)
            continue
        if choice == "structure":
            self._refine_participant_structure(participant_id)


def install_change_impact_refinement_support() -> None:
    """Install rename/delete refinement without changing the public app composition."""
    FocusedRefinementMixin._refine_selected_action = _refine_selected_action_with_edit
    FocusedRefinementMixin._refine_selected_participant = _refine_selected_participant_with_edit
