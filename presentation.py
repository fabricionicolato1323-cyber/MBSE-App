from __future__ import annotations

from typing import Any


_NATURE_LABELS = {
    "human_individual": "individual person or role",
    "organization": "organization",
    "organizational_unit": "organizational unit",
    "team_or_collective": "team or collective",
    "existing_technical_system": "external technical participant",
    "infrastructure_or_facility": "facility or infrastructure",
    "external_operational_service": "external service",
    "population_or_community": "population or community",
    "environmental_participant": "environmental participant",
    "unspecified": "participant or context",
}


def friendly_participant_kind(data: dict[str, Any]) -> str:
    nature = str(data.get("nature", "unspecified"))
    if data.get("type") == "OperationalActor":
        return "individual person or role"
    return _NATURE_LABELS.get(nature, "participant or context")


def _format_characteristic(characteristic: dict[str, Any]) -> str:
    name = characteristic.get("name", "Characteristic")
    value_type = characteristic.get("value_type")
    if value_type == "range":
        value = (
            f"{characteristic.get('lower_bound')} .. "
            f"{characteristic.get('upper_bound')}"
        )
        unit = str(characteristic.get("unit", "")).strip()
    elif value_type == "number":
        value = str(characteristic.get("value", ""))
        unit = str(characteristic.get("unit", "")).strip()
    else:
        value = str(characteristic.get("value", ""))
        unit = ""
    return f"{name}: {value}{(' ' + unit) if unit else ''}"


def _hierarchy_lines(model, node_ids: list[str]) -> list[str]:
    node_set = set(node_ids)
    roots = [
        node_id
        for node_id in node_ids
        if model.decomposition_parent(node_id) not in node_set
    ]
    lines: list[str] = []
    visited: set[str] = set()

    def walk(node_id: str, depth: int) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        lines.append(f"    {'  ' * depth}- {model.name(node_id)}")
        for child in model.decomposition_children(node_id):
            if child in node_set:
                walk(child, depth + 1)

    for root in roots:
        if model.decomposition_children(root):
            walk(root, 0)

    for node_id in node_ids:
        if node_id not in visited and model.decomposition_children(node_id):
            walk(node_id, 0)
    return lines


def friendly_model_view(model) -> str:
    """Show the complete user-facing model without internal ontology labels."""
    lines = ["", "MODEL SO FAR", "=" * 64]

    goals = model.nodes_of_type("OperationalCapability")
    active_participants = model.active_participants()
    context = model.context_entities()
    actions = model.nodes_of_type("OperationalActivity")

    lines.append("\nGoals")
    lines.extend([f"  - {model.name(node)}" for node in goals] or ["  (none)"])

    lines.append("\nParticipants")
    if active_participants:
        for node_id in active_participants:
            data = model.graph.nodes[node_id]
            lines.append(
                f"  - {model.name(node_id)} — {friendly_participant_kind(data)}"
            )
    else:
        lines.append("  (none)")

    lines.append("\nPlaces / context")
    if context:
        for node_id in context:
            data = model.graph.nodes[node_id]
            lines.append(
                f"  - {model.name(node_id)} — {friendly_participant_kind(data)}"
            )
    else:
        lines.append("  (none)")

    lines.append("\nActions")
    if actions:
        for action_id in actions:
            performers = model.participants_for_activity(action_id)
            if performers:
                names = ", ".join(model.name(item) for item in performers)
                lines.append(f"  - {names} -> {model.name(action_id)}")
            else:
                lines.append(f"  - {model.name(action_id)}")

            semantics = model.activity_semantics(action_id)
            semantic_labels = (
                ("semantic_objects", "objects"),
                ("semantic_recipients", "recipients"),
                ("semantic_locations", "locations"),
                ("semantic_conditions", "conditions"),
                ("semantic_time", "time"),
                ("semantic_other_complements", "other"),
            )
            for field, label in semantic_labels:
                values = semantics.get(field)
                if values:
                    lines.append(f"      {label}: {', '.join(values)}")
    else:
        lines.append("  (none)")

    lines.append("\nInteractions")
    exchanges = model.exchanges()
    if exchanges:
        for source, target, name in exchanges:
            lines.append(
                f"  - {model.name(source)} --[{name}]--> {model.name(target)}"
            )
    else:
        lines.append("  (none)")

    lines.append("\nCommunication")
    means = model.communication_means()
    if means:
        for source, target, name in means:
            lines.append(
                f"  - {model.name(source)} <--[{name}]--> {model.name(target)}"
            )
    else:
        lines.append("  (none)")

    hierarchy_groups = [
        ("Goals", goals),
        ("Actions", actions),
        ("Participants / context", model.participants()),
    ]
    hierarchy_sections: list[str] = []
    for title, node_ids in hierarchy_groups:
        tree = _hierarchy_lines(model, node_ids)
        if tree:
            hierarchy_sections.append(f"  {title}")
            hierarchy_sections.extend(tree)

    if hierarchy_sections:
        lines.extend(
            [
                "",
                "Composition / decomposition",
                "-" * 64,
                *hierarchy_sections,
            ]
        )

    characteristic_lines: list[str] = []
    user_labels = {
        "OperationalCapability": "Goal",
        "OperationalActivity": "Action",
        "OperationalActor": "Participant",
        "OperationalEntity": "Participant / context",
    }
    for node_id, data in model.graph.nodes(data=True):
        values = model.characteristics_for_node(node_id)
        if not values:
            continue
        label = user_labels.get(data.get("type"), "Item")
        characteristic_lines.append(f"  {label}: {model.name(node_id)}")
        for item in values:
            characteristic_lines.append(f"    - {_format_characteristic(item)}")

    for source, target, key, name in model.exchange_records():
        values = model.characteristics_for_exchange(source, target, key)
        if not values:
            continue
        characteristic_lines.append(
            f"  Interaction: {name} "
            f"({model.name(source)} -> {model.name(target)})"
        )
        for item in values:
            characteristic_lines.append(f"    - {_format_characteristic(item)}")

    if characteristic_lines:
        lines.extend(
            [
                "",
                "Characteristics",
                "-" * 64,
                *characteristic_lines,
            ]
        )

    lines.extend(
        [
            "",
            (
                f"Items: {model.graph.number_of_nodes()} | "
                f"Connections: {model.graph.number_of_edges()}"
            ),
            "=" * 64,
        ]
    )
    return "\n".join(lines)
