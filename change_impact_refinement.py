from __future__ import annotations

from typing import Any
from urllib.parse import quote

from focused_refinement import FocusedRefinementMixin


PRESENTATION_KEY = "_revision_presentation"
_REFERENCE_NAME_PAIRS = (
    ("activity_id", "activity_name"),
    ("source_activity_id", "source_activity_name"),
    ("target_activity_id", "target_activity_name"),
    ("participant_id", "participant_name"),
    ("source_participant_id", "source_participant_name"),
    ("target_participant_id", "target_participant_name"),
    ("node_id", "node_name"),
    ("element_id", "element_name"),
)


def _clean_name(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _node_info(model: Any, node_id: str, *, fallback_name: str = "") -> dict[str, str]:
    data = model.graph.nodes.get(node_id, {}) if node_id in model.graph else {}
    return {
        "kind": "node",
        "id": str(node_id),
        "name": _clean_name(data.get("name") or fallback_name or node_id),
        "type": str(data.get("type") or ""),
    }


def _contains_reference_id(value: Any, node_id: str) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).endswith("_id") and str(item) == str(node_id):
                return True
            if _contains_reference_id(item, node_id):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_reference_id(item, node_id) for item in value)
    return False


def directly_impacted_node_ids(model: Any, node_id: str) -> list[str]:
    """Return graph nodes directly connected to one changed model element."""
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


def _js_uri_component(value: Any) -> str:
    return quote(str(value), safe="-_.!~*'()")


def _edge_visual_id(
    source: Any,
    target: Any,
    key: Any,
    data: dict[str, Any],
    index: int,
) -> str:
    existing = _clean_name(data.get("id"))
    if existing:
        return existing
    if key is not None and str(key) != "":
        discriminator = f"key:{key}"
    elif _clean_name(data.get("name")):
        discriminator = f"name:{_clean_name(data.get('name'))}"
    else:
        discriminator = f"index:{index}"
    parts = [
        _clean_name(data.get("type")) or "EDGE",
        _clean_name(source) or "source",
        _clean_name(target) or "target",
        discriminator,
    ]
    return "oa-edge:" + ":".join(_js_uri_component(part) for part in parts)


def directly_impacted_relations(model: Any, node_id: str) -> list[dict[str, str]]:
    """Return relationships whose semantics or explicit references depend on node_id."""
    impacted: list[dict[str, str]] = []
    for index, (source, target, key, data) in enumerate(
        model.graph.edges(keys=True, data=True)
    ):
        if source != node_id and target != node_id and not _contains_reference_id(data, node_id):
            continue
        relation_type = str(data.get("type") or "")
        impacted.append(
            {
                "kind": "edge",
                "id": _edge_visual_id(source, target, key, data, index),
                "name": _clean_name(data.get("name") or relation_type or "Relationship"),
                "type": relation_type,
                "source": str(source),
                "target": str(target),
            }
        )
    return impacted


def _persist_if_web_model(model: Any) -> None:
    persist = getattr(model, "_persist", None)
    if callable(persist):
        persist()


def set_change_presentation(
    model: Any,
    *,
    operation: str,
    modified: list[dict[str, Any]],
    impacted_ids: list[str],
    impacted_relations: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    impacted = [
        _node_info(model, node_id)
        for node_id in impacted_ids
        if node_id in model.graph
    ]
    relations = [dict(item) for item in (impacted_relations or [])]
    presentation: dict[str, Any] = {
        "operation": str(operation),
        "modified": [dict(item) for item in modified],
        "impacted": impacted,
        "impacted_relations": relations,
        "modified_ids": [str(item.get("id") or "") for item in modified],
        "impacted_ids": [item["id"] for item in impacted],
        "impacted_relation_ids": [str(item.get("id") or "") for item in relations],
    }
    if extra:
        presentation.update(extra)
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


def _validate_rename(model: Any, node_id: str, new_name: str) -> tuple[str, str, str]:
    if node_id not in model.graph:
        return "", "", "The selected model element no longer exists."
    normalized = _clean_name(new_name)
    if not normalized:
        return "", "", "The new name cannot be empty."
    current = _clean_name(model.graph.nodes[node_id].get("name") or node_id)
    if normalized.casefold() == current.casefold():
        return current, normalized, "The new name is the same as the current name."
    duplicate = _duplicate_for_name(model, node_id, normalized)
    if duplicate:
        return current, normalized, f"'{normalized}' is already used by another compatible model element."
    return current, normalized, ""


def preview_rename_model_node(
    model: Any,
    node_id: str,
    new_name: str,
) -> tuple[bool, str, dict[str, Any]]:
    """Publish a rename projection without mutating the semantic model."""
    current, normalized, error = _validate_rename(model, node_id, new_name)
    if error:
        return False, error, {}
    impacted_ids = directly_impacted_node_ids(model, node_id)
    modified = _node_info(model, node_id)
    modified["old_name"] = current
    modified["name"] = normalized
    presentation = set_change_presentation(
        model,
        operation="rename_preview",
        modified=[modified],
        impacted_ids=impacted_ids,
        impacted_relations=directly_impacted_relations(model, node_id),
        extra={"preview_node_names": {str(node_id): normalized}},
    )
    return True, "", presentation


def _propagate_cached_reference_names(model: Any, node_id: str, new_name: str) -> int:
    """Update redundant display-name caches only when a sibling ID proves identity.

    Authoritative references remain IDs. This helper does not perform free-text
    replacement; it only updates an explicit ``*_name`` field paired with a
    matching ``*_id`` field. Current activity/scenario references are already
    ID-based, but this keeps future cached labels consistent without ambiguity.
    """
    changed = 0

    def walk(value: Any) -> None:
        nonlocal changed
        if isinstance(value, dict):
            for id_key, name_key in _REFERENCE_NAME_PAIRS:
                if str(value.get(id_key) or "") == str(node_id) and name_key in value:
                    if _clean_name(value.get(name_key)) != new_name:
                        value[name_key] = new_name
                        changed += 1
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(model.graph.graph)
    for other_id, data in model.graph.nodes(data=True):
        if other_id != node_id:
            walk(data)
    for _source, _target, _key, data in model.graph.edges(keys=True, data=True):
        walk(data)
    return changed


def rename_model_node(model: Any, node_id: str, new_name: str) -> tuple[bool, str, dict[str, Any]]:
    """Commit a confirmed rename as one graph checkpoint using the stable node ID."""
    current, normalized, error = _validate_rename(model, node_id, new_name)
    if error:
        return False, error, {}

    impacted_ids = directly_impacted_node_ids(model, node_id)
    impacted_relations = directly_impacted_relations(model, node_id)
    checkpoint = getattr(model, "_checkpoint", None)
    if callable(checkpoint):
        checkpoint()
    model.graph.nodes[node_id]["name"] = normalized
    propagated = _propagate_cached_reference_names(model, node_id, normalized)

    modified = _node_info(model, node_id)
    modified["old_name"] = current
    presentation = set_change_presentation(
        model,
        operation="rename",
        modified=[modified],
        impacted_ids=impacted_ids,
        impacted_relations=impacted_relations,
        extra={"propagated_name_copies": propagated},
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
        impacted_relations=directly_impacted_relations(model, node_id),
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
    impacted_relations = directly_impacted_relations(model, node_id)

    checkpoint = getattr(model, "_checkpoint", None)
    if callable(checkpoint):
        checkpoint()
    model.graph.remove_node(node_id)

    presentation = {
        "operation": "delete",
        "modified": [deleted],
        "impacted": impacted_before,
        "impacted_relations": impacted_relations,
        "modified_ids": [deleted["id"]],
        "impacted_ids": [item["id"] for item in impacted_before],
        "impacted_relation_ids": [item["id"] for item in impacted_relations],
    }
    model.graph.graph[PRESENTATION_KEY] = presentation
    _persist_if_web_model(model)
    return True, "", presentation


def _impact_names(presentation: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for key in ("impacted", "impacted_relations"):
        result.extend(
            _clean_name(item.get("name"))
            for item in presentation.get(key, [])
            if isinstance(item, dict) and _clean_name(item.get("name"))
        )
    return list(dict.fromkeys(result))


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

    ok, error, preview = preview_rename_model_node(self.model, node_id, new_name)
    if not ok:
        self.add_notice(f"Rename preview was not created: {error}")
        return

    impacted = _impact_names(preview)
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
        clear_change_presentation(self.model)
        self.add_notice("Rename cancelled. Nothing was changed.")
        return

    ok, error, presentation = rename_model_node(self.model, node_id, new_name)
    if not ok:
        clear_change_presentation(self.model)
        self.add_notice(f"Rename was not applied: {error}")
        return

    propagated = int(presentation.get("propagated_name_copies") or 0)
    suffix = (
        f" Updated {propagated} redundant display-name reference(s) linked by ID."
        if propagated
        else " All semantic references already resolve by stable ID."
    )
    self.add_notice(
        f"Renamed '{old_name}' to '{new_name}'. Changed element: red; directly affected "
        f"items remain orange for review.{suffix}"
    )


def _delete_selected(self: Any, node_id: str, friendly_kind: str) -> None:
    name = self.model.name(node_id)
    presentation = preview_delete_model_node(self.model, node_id)
    impacted = _impact_names(presentation)
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
        clear_change_presentation(self.model)
        self.add_notice("Delete cancelled. Nothing was removed.")
        return

    ok, error, _presentation = delete_model_node(self.model, node_id)
    if not ok:
        self.add_notice(f"Delete was not applied: {error}")
        return
    self.add_notice(
        f"Deleted {friendly_kind} '{name}'. Directly affected remaining items stay orange for review."
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
