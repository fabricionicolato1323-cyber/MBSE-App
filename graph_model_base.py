from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from ontology import (
    ALLOWED_RELATIONS,
    NODE_TYPES,
    PARTICIPANT_NATURES,
    PARTICIPANT_TYPES,
)


def _canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


class OAGraph:
    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph(model="Arcadia Operational Analysis")
        self._history: list[nx.MultiDiGraph] = []

    def _checkpoint(self) -> None:
        self._history.append(copy.deepcopy(self.graph))
        if len(self._history) > 50:
            self._history.pop(0)

    def undo(self) -> bool:
        if not self._history:
            return False
        self.graph = self._history.pop()
        return True

    def _new_id(self, node_type: str, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "element"
        candidate = f"{node_type}:{base}"
        if candidate not in self.graph:
            return candidate
        index = 2
        while f"{candidate}-{index}" in self.graph:
            index += 1
        return f"{candidate}-{index}"

    def find_duplicate(self, node_type: str, name: str) -> str | None:
        wanted = _canonical(name)
        for node_id, data in self.graph.nodes(data=True):
            if (
                data.get("type") == node_type
                and _canonical(data.get("name", "")) == wanted
            ):
                return node_id
        return None

    def find_participant_duplicate(self, name: str) -> str | None:
        wanted = _canonical(name)
        for node_id, data in self.graph.nodes(data=True):
            if (
                data.get("type") in PARTICIPANT_TYPES
                and _canonical(data.get("name", "")) == wanted
            ):
                return node_id
        return None

    def add_node(
        self,
        node_type: str,
        name: str,
        *,
        expects_activity: bool | None = None,
        **attributes,
    ) -> tuple[bool, str, str]:
        if node_type not in NODE_TYPES:
            return False, "", "Unsupported internal model element."

        if node_type in PARTICIPANT_TYPES:
            duplicate = self.find_participant_duplicate(name)
        else:
            duplicate = self.find_duplicate(node_type, name)

        if duplicate:
            return False, duplicate, f"'{name}' is already in the model."

        self._checkpoint()
        node_id = self._new_id(node_type, name)

        node_attributes = {"type": node_type, "name": name}
        if node_type == "OperationalActor":
            node_attributes["expects_activity"] = True
            node_attributes["nature"] = "human_individual"
        elif node_type == "OperationalEntity":
            node_attributes["expects_activity"] = (
                True if expects_activity is None else bool(expects_activity)
            )
            node_attributes["nature"] = "unspecified"

        node_attributes.update(attributes)
        if node_type in PARTICIPANT_TYPES:
            nature = node_attributes.get("nature", "unspecified")
            if nature not in PARTICIPANT_NATURES:
                return False, "", f"Unsupported participant nature: {nature}."
            if node_type == "OperationalActor" and nature != "human_individual":
                return (
                    False,
                    "",
                    "An Operational Actor must be one indivisible human participant.",
                )
            if node_type == "OperationalEntity" and nature == "human_individual":
                return (
                    False,
                    "",
                    "A human individual must be modeled as an Operational Actor.",
                )
        self.graph.add_node(node_id, **node_attributes)
        return True, node_id, ""

    def update_node_attributes(self, node_id: str, **attributes) -> bool:
        if node_id not in self.graph or not attributes:
            return False
        self._checkpoint()
        self.graph.nodes[node_id].update(attributes)
        return True

    def _relation_graph(self, relation: str) -> nx.DiGraph:
        relation_graph = nx.DiGraph()
        for source, target, data in self.graph.edges(data=True):
            if data.get("type") == relation:
                relation_graph.add_edge(source, target)
        return relation_graph

    def _would_create_cycle(
        self,
        source_id: str,
        target_id: str,
        relation: str,
    ) -> bool:
        if source_id == target_id:
            return True
        relation_graph = self._relation_graph(relation)
        if target_id not in relation_graph or source_id not in relation_graph:
            return False
        return nx.has_path(relation_graph, target_id, source_id)

    def structural_parent(self, node_id: str) -> str | None:
        for source, _, data in self.graph.in_edges(node_id, data=True):
            if data.get("type") == "CONTAINS":
                return source
        return None

    def locations_for(self, node_id: str) -> list[str]:
        return [
            target
            for _, target, data in self.graph.out_edges(node_id, data=True)
            if data.get("type") == "LOCATED_IN"
        ]

    def expects_activity(self, node_id: str) -> bool:
        data = self.graph.nodes[node_id]
        if data.get("type") == "OperationalActor":
            return True
        if data.get("type") == "OperationalEntity":
            return bool(data.get("expects_activity", True))
        return False

    def has_relation(
        self,
        source_id: str,
        relation: str,
        target_id: str,
    ) -> bool:
        if source_id not in self.graph or target_id not in self.graph:
            return False
        for _, existing_target, data in self.graph.out_edges(source_id, data=True):
            if existing_target == target_id and data.get("type") == relation:
                return True
        return False

    def add_relation(
        self,
        source_id: str,
        relation: str,
        target_id: str,
        **attributes,
    ) -> tuple[bool, str]:
        if source_id not in self.graph or target_id not in self.graph:
            return False, "Both model elements must already exist."

        source_type = self.graph.nodes[source_id]["type"]
        target_type = self.graph.nodes[target_id]["type"]
        signature = (source_type, relation, target_type)
        if signature not in ALLOWED_RELATIONS:
            return False, "That connection is not allowed by the model rules."

        if relation in {"CONTAINS", "LOCATED_IN"} and source_id == target_id:
            return False, "An element cannot contain or locate itself."

        if relation == "CONTAINS":
            if self.structural_parent(target_id):
                return False, "That element is already part of another structural parent."
            if self._would_create_cycle(source_id, target_id, "CONTAINS"):
                return False, "That structural connection would create a containment cycle."

        if relation == "LOCATED_IN":
            if self._would_create_cycle(source_id, target_id, "LOCATED_IN"):
                return False, "That location connection would create a location cycle."

        for _, existing_target, _, data in self.graph.out_edges(
            source_id,
            keys=True,
            data=True,
        ):
            if existing_target != target_id or data.get("type") != relation:
                continue
            same_name = _canonical(data.get("name", "")) == _canonical(
                attributes.get("name", "")
            )
            if (
                relation in {"OPERATIONAL_EXCHANGE", "COMMUNICATION_MEAN"}
                and same_name
            ):
                return False, "The same connection already exists."
            if relation not in {"OPERATIONAL_EXCHANGE", "COMMUNICATION_MEAN"}:
                return False, "That connection already exists."

        self._checkpoint()
        self.graph.add_edge(
            source_id,
            target_id,
            type=relation,
            **attributes,
        )
        return True, ""

    def nodes_of_type(self, *types: str) -> list[str]:
        wanted = set(types)
        return [
            node_id
            for node_id, data in self.graph.nodes(data=True)
            if data.get("type") in wanted
        ]

    def participants(self) -> list[str]:
        return self.nodes_of_type(*PARTICIPANT_TYPES)

    def active_participants(self) -> list[str]:
        return [
            node_id
            for node_id in self.participants()
            if self.expects_activity(node_id)
        ]

    def context_entities(self) -> list[str]:
        return [
            node_id
            for node_id in self.nodes_of_type("OperationalEntity")
            if not self.expects_activity(node_id)
        ]

    def name(self, node_id: str) -> str:
        return self.graph.nodes[node_id].get("name", node_id)

    def participant_label(self, node_id: str) -> str:
        data = self.graph.nodes[node_id]
        return (
            f"{self.name(node_id)} "
            f"[{data.get('type')}; {data.get('nature', 'unspecified')}; "
            f"{data.get('status', 'confirmed')}]"
        )

    def participants_for_activity(self, activity_id: str) -> list[str]:
        return [
            source
            for source, _, data in self.graph.in_edges(activity_id, data=True)
            if data.get("type") == "PERFORMS"
        ]

    def participant_for_activity(self, activity_id: str) -> str | None:
        performers = self.participants_for_activity(activity_id)
        return performers[0] if performers else None

    def actions_for_participant(self, participant_id: str) -> list[str]:
        return [
            target
            for _, target, data in self.graph.out_edges(participant_id, data=True)
            if data.get("type") == "PERFORMS"
        ]

    def activity_semantics(self, activity_id: str) -> dict:
        if activity_id not in self.graph:
            return {}
        data = self.graph.nodes[activity_id]
        fields = (
            "semantic_verb",
            "semantic_objects",
            "semantic_recipients",
            "semantic_locations",
            "semantic_conditions",
            "semantic_time",
            "semantic_other_complements",
            "source_text",
        )
        return {field: data.get(field) for field in fields if data.get(field)}

    def action_label(self, activity_id: str) -> str:
        performers = self.participants_for_activity(activity_id)
        if performers:
            names = ", ".join(self.name(node_id) for node_id in performers)
            return f"{self.name(activity_id)} — {names}"
        return self.name(activity_id)

    def short_context(self, limit: int = 14) -> str:
        items = []
        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get("type")
            if node_type == "OperationalCapability":
                friendly = "goal"
            elif node_type == "OperationalActivity":
                friendly = "action"
            elif (
                node_type in PARTICIPANT_TYPES
                and not self.expects_activity(node_id)
            ):
                friendly = "place/context"
            elif node_type in PARTICIPANT_TYPES:
                friendly = "participant"
            else:
                friendly = "item"

            items.append(f"{data.get('name')} ({friendly})")
            if len(items) >= limit:
                break
        return ", ".join(items) if items else "No model elements yet."

    def exchanges(self) -> list[tuple[str, str, str]]:
        result = []
        for source, target, data in self.graph.edges(data=True):
            if data.get("type") == "OPERATIONAL_EXCHANGE":
                result.append(
                    (
                        source,
                        target,
                        data.get("name", "Interaction"),
                    )
                )
        return result

    def communication_means(self) -> list[tuple[str, str, str]]:
        result = []
        for source, target, data in self.graph.edges(data=True):
            if data.get("type") == "COMMUNICATION_MEAN":
                result.append(
                    (
                        source,
                        target,
                        data.get("name", "Communication"),
                    )
                )
        return result

    def containment_relations(self) -> list[tuple[str, str]]:
        return [
            (source, target)
            for source, target, data in self.graph.edges(data=True)
            if data.get("type") == "CONTAINS"
        ]

    def location_relations(self) -> list[tuple[str, str]]:
        return [
            (source, target)
            for source, target, data in self.graph.edges(data=True)
            if data.get("type") == "LOCATED_IN"
        ]

    def has_communication_between(
        self,
        source_participant: str,
        target_participant: str,
        name: str = "",
    ) -> bool:
        wanted = _canonical(name)
        for _, target, data in self.graph.out_edges(
            source_participant,
            data=True,
        ):
            if (
                target != target_participant
                or data.get("type") != "COMMUNICATION_MEAN"
            ):
                continue
            if not name or _canonical(data.get("name", "")) == wanted:
                return True
        for _, target, data in self.graph.out_edges(
            target_participant,
            data=True,
        ):
            if (
                target != source_participant
                or data.get("type") != "COMMUNICATION_MEAN"
            ):
                continue
            if not name or _canonical(data.get("name", "")) == wanted:
                return True
        return False

    def friendly_show(self) -> str:
        lines = ["", "MODEL SO FAR", "=" * 64]

        goals = self.nodes_of_type("OperationalCapability")
        participants = self.active_participants()
        context = self.context_entities()
        actions = self.nodes_of_type("OperationalActivity")

        lines.append("\nGoals")
        lines.extend(
            [f"  - {self.name(node)}" for node in goals]
            or ["  (none)"]
        )

        lines.append("\nParticipants")
        lines.extend(
            [f"  - {self.participant_label(node)}" for node in participants]
            or ["  (none)"]
        )

        lines.append("\nPlaces / context")
        lines.extend(
            [f"  - {self.participant_label(node)}" for node in context]
            or ["  (none)"]
        )

        lines.append("\nStructure")
        containment = self.containment_relations()
        if containment:
            for parent, child in containment:
                lines.append(
                    f"  - {self.name(parent)} contains {self.name(child)}"
                )
        else:
            lines.append("  (none)")

        lines.append("\nLocation")
        locations = self.location_relations()
        if locations:
            for item, place in locations:
                if self.expects_activity(item):
                    relation_text = "operates in"
                else:
                    relation_text = "is located in"
                lines.append(
                    f"  - {self.name(item)} {relation_text} {self.name(place)}"
                )
        else:
            lines.append("  (none)")

        lines.append("\nActions")
        if actions:
            for action in actions:
                performers = self.participants_for_activity(action)
                if performers:
                    performer_names = ", ".join(
                        self.name(node_id) for node_id in performers
                    )
                    lines.append(
                        f"  - {performer_names} -> {self.name(action)}"
                    )
                else:
                    lines.append(f"  - {self.name(action)}")

                semantics = self.activity_semantics(action)
                if semantics.get("semantic_objects"):
                    lines.append(
                        "      objects: "
                        + ", ".join(semantics["semantic_objects"])
                    )
                if semantics.get("semantic_recipients"):
                    lines.append(
                        "      recipients: "
                        + ", ".join(semantics["semantic_recipients"])
                    )
                if semantics.get("semantic_locations"):
                    lines.append(
                        "      locations: "
                        + ", ".join(semantics["semantic_locations"])
                    )
                if semantics.get("semantic_conditions"):
                    lines.append(
                        "      conditions: "
                        + ", ".join(semantics["semantic_conditions"])
                    )
                if semantics.get("semantic_time"):
                    lines.append(
                        "      time: "
                        + ", ".join(semantics["semantic_time"])
                    )
        else:
            lines.append("  (none)")

        lines.append("\nInteractions")
        exchanges = self.exchanges()
        if exchanges:
            for source, target, name in exchanges:
                lines.append(
                    f"  - {self.name(source)} --[{name}]--> {self.name(target)}"
                )
        else:
            lines.append("  (none)")

        lines.append("\nCommunication")
        means = self.communication_means()
        if means:
            for source, target, name in means:
                lines.append(
                    f"  - {self.name(source)} <--[{name}]--> {self.name(target)}"
                )
        else:
            lines.append("  (none)")

        lines.extend(
            [
                "",
                (
                    f"Items: {self.graph.number_of_nodes()} | "
                    f"Connections: {self.graph.number_of_edges()}"
                ),
                "=" * 64,
            ]
        )
        return "\n".join(lines)

    def completeness_messages(self) -> list[str]:
        messages: list[str] = []
        goals = self.nodes_of_type("OperationalCapability")
        participants = self.participants()
        actions = self.nodes_of_type("OperationalActivity")

        if not goals:
            messages.append("The main operational goal is still missing.")
        if not participants:
            messages.append(
                "No participant or context element has been identified yet."
            )
        if not actions:
            messages.append("No operational action has been described yet.")

        for participant in participants:
            if (
                self.expects_activity(participant)
                and not self.actions_for_participant(participant)
            ):
                messages.append(
                    f"'{self.name(participant)}' has no action yet."
                )

        for action in actions:
            performers = self.participants_for_activity(action)
            if not performers:
                messages.append(
                    f"'{self.name(action)}' is not assigned to anyone yet."
                )
            supports = any(
                data.get("type") == "SUPPORTS_CAPABILITY"
                for _, _, data in self.graph.out_edges(action, data=True)
            )
            if goals and not supports:
                messages.append(
                    f"'{self.name(action)}' is not connected to a goal yet."
                )

        return messages

    def save(self, path: str) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        data = json_graph.node_link_data(self.graph, edges="edges")
        output.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return output
