from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from ontology import ALLOWED_RELATIONS, NODE_TYPES, PARTICIPANT_TYPES


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
            if data.get("type") == node_type and _canonical(data.get("name", "")) == wanted:
                return node_id
        return None

    def find_participant_duplicate(self, name: str) -> str | None:
        wanted = _canonical(name)
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") in PARTICIPANT_TYPES and _canonical(data.get("name", "")) == wanted:
                return node_id
        return None

    def add_node(self, node_type: str, name: str) -> tuple[bool, str, str]:
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
        self.graph.add_node(node_id, type=node_type, name=name)
        return True, node_id, ""

    def add_relation(self, source_id: str, relation: str, target_id: str, **attributes) -> tuple[bool, str]:
        if source_id not in self.graph or target_id not in self.graph:
            return False, "Both model elements must already exist."

        source_type = self.graph.nodes[source_id]["type"]
        target_type = self.graph.nodes[target_id]["type"]
        signature = (source_type, relation, target_type)
        if signature not in ALLOWED_RELATIONS:
            return False, "That connection is not allowed by the model rules."

        for _, existing_target, _, data in self.graph.out_edges(source_id, keys=True, data=True):
            if existing_target != target_id or data.get("type") != relation:
                continue
            same_name = _canonical(data.get("name", "")) == _canonical(attributes.get("name", ""))
            if relation in {"OPERATIONAL_EXCHANGE", "COMMUNICATION_MEAN"} and same_name:
                return False, "The same connection already exists."
            if relation not in {"OPERATIONAL_EXCHANGE", "COMMUNICATION_MEAN"}:
                return False, "That connection already exists."

        self._checkpoint()
        self.graph.add_edge(source_id, target_id, type=relation, **attributes)
        return True, ""

    def nodes_of_type(self, *types: str) -> list[str]:
        wanted = set(types)
        return [node_id for node_id, data in self.graph.nodes(data=True) if data.get("type") in wanted]

    def participants(self) -> list[str]:
        return self.nodes_of_type(*PARTICIPANT_TYPES)

    def name(self, node_id: str) -> str:
        return self.graph.nodes[node_id].get("name", node_id)

    def participant_for_activity(self, activity_id: str) -> str | None:
        for source, _, data in self.graph.in_edges(activity_id, data=True):
            if data.get("type") == "PERFORMS":
                return source
        return None

    def actions_for_participant(self, participant_id: str) -> list[str]:
        return [
            target
            for _, target, data in self.graph.out_edges(participant_id, data=True)
            if data.get("type") == "PERFORMS"
        ]

    def action_label(self, activity_id: str) -> str:
        performer = self.participant_for_activity(activity_id)
        if performer:
            return f"{self.name(activity_id)} — {self.name(performer)}"
        return self.name(activity_id)

    def short_context(self, limit: int = 14) -> str:
        items = []
        friendly = {
            "OperationalCapability": "goal",
            "OperationalActor": "participant",
            "OperationalEntity": "participant",
            "OperationalActivity": "action",
        }
        for _, data in self.graph.nodes(data=True):
            items.append(f"{data.get('name')} ({friendly.get(data.get('type'), 'item')})")
            if len(items) >= limit:
                break
        return ", ".join(items) if items else "No model elements yet."

    def exchanges(self) -> list[tuple[str, str, str]]:
        result = []
        for source, target, data in self.graph.edges(data=True):
            if data.get("type") == "OPERATIONAL_EXCHANGE":
                result.append((source, target, data.get("name", "Interaction")))
        return result

    def communication_means(self) -> list[tuple[str, str, str]]:
        result = []
        for source, target, data in self.graph.edges(data=True):
            if data.get("type") == "COMMUNICATION_MEAN":
                result.append((source, target, data.get("name", "Communication")))
        return result

    def has_communication_between(self, source_participant: str, target_participant: str, name: str = "") -> bool:
        wanted = _canonical(name)
        for _, target, data in self.graph.out_edges(source_participant, data=True):
            if target != target_participant or data.get("type") != "COMMUNICATION_MEAN":
                continue
            if not name or _canonical(data.get("name", "")) == wanted:
                return True
        for _, target, data in self.graph.out_edges(target_participant, data=True):
            if target != source_participant or data.get("type") != "COMMUNICATION_MEAN":
                continue
            if not name or _canonical(data.get("name", "")) == wanted:
                return True
        return False

    def friendly_show(self) -> str:
        lines = ["", "MODEL SO FAR", "=" * 64]

        goals = self.nodes_of_type("OperationalCapability")
        participants = self.participants()
        actions = self.nodes_of_type("OperationalActivity")

        lines.append("\nGoals")
        lines.extend([f"  - {self.name(node)}" for node in goals] or ["  (none)"])

        lines.append("\nParticipants")
        lines.extend([f"  - {self.name(node)}" for node in participants] or ["  (none)"])

        lines.append("\nActions")
        if actions:
            for action in actions:
                performer = self.participant_for_activity(action)
                if performer:
                    lines.append(f"  - {self.name(performer)} -> {self.name(action)}")
                else:
                    lines.append(f"  - {self.name(action)}")
        else:
            lines.append("  (none)")

        lines.append("\nInteractions")
        exchanges = self.exchanges()
        if exchanges:
            for source, target, name in exchanges:
                lines.append(f"  - {self.name(source)} --[{name}]--> {self.name(target)}")
        else:
            lines.append("  (none)")

        lines.append("\nCommunication")
        means = self.communication_means()
        if means:
            for source, target, name in means:
                lines.append(f"  - {self.name(source)} <--[{name}]--> {self.name(target)}")
        else:
            lines.append("  (none)")

        lines.extend([
            "",
            f"Items: {self.graph.number_of_nodes()} | Connections: {self.graph.number_of_edges()}",
            "=" * 64,
        ])
        return "\n".join(lines)

    def completeness_messages(self) -> list[str]:
        messages: list[str] = []
        goals = self.nodes_of_type("OperationalCapability")
        participants = self.participants()
        actions = self.nodes_of_type("OperationalActivity")

        if not goals:
            messages.append("The main operational goal is still missing.")
        if not participants:
            messages.append("No participant has been identified yet.")
        if not actions:
            messages.append("No operational action has been described yet.")

        for participant in participants:
            if not self.actions_for_participant(participant):
                messages.append(f"'{self.name(participant)}' has no action yet.")

        for action in actions:
            performer = self.participant_for_activity(action)
            if not performer:
                messages.append(f"'{self.name(action)}' is not assigned to anyone yet.")
            supports = any(
                data.get("type") == "SUPPORTS_CAPABILITY"
                for _, _, data in self.graph.out_edges(action, data=True)
            )
            if goals and not supports:
                messages.append(f"'{self.name(action)}' is not connected to a goal yet.")

        return messages

    def save(self, path: str) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        data = json_graph.node_link_data(self.graph, edges="edges")
        output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return output
