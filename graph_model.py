"""Persistent NetworkX model and deterministic write barrier for OA."""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from ontology import (
    AGGREGATION_RULES,
    ALLOWED_RELATIONS,
    COMPOSITION_RELATIONS,
    CONCEPT_GUIDANCE,
    CONSTRAINT_OPERATORS,
    CONSTRAINT_SCOPES,
    ENDPOINT_RELATIONS,
    NODE_TYPES,
    PARTICIPANT_TYPES,
    RELATION_GUIDANCE,
    ontology_catalog,
    validate_concept_name,
)


SCHEMA_VERSION = 2


def _canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class OAGraph:
    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph(
            model="Arcadia Operational Analysis",
            schema_version=SCHEMA_VERSION,
        )
        self._history: list[nx.MultiDiGraph] = []

    def _checkpoint(self) -> None:
        self._history.append(copy.deepcopy(self.graph))
        if len(self._history) > 100:
            self._history.pop(0)

    def undo(self) -> bool:
        if not self._history:
            return False
        self.graph = self._history.pop()
        return True

    def find_duplicate(
        self,
        node_type: str,
        name: str,
        exclude_id: str | None = None,
    ) -> str | None:
        wanted = _canonical(name)
        for node_id, data in self.graph.nodes(data=True):
            if node_id == exclude_id:
                continue
            same_participant_family = (
                node_type in PARTICIPANT_TYPES
                and data.get("type") in PARTICIPANT_TYPES
            )
            if (
                (same_participant_family or data.get("type") == node_type)
                and _canonical(str(data.get("name", ""))) == wanted
            ):
                return node_id
        return None

    @staticmethod
    def _validate_parameter(parameter: dict) -> tuple[bool, str]:
        required = ("id", "name", "description", "quantityKind", "valueType", "unit")
        missing = [field for field in required if not str(parameter.get(field, "")).strip()]
        if missing:
            return False, "Parameter is missing: " + ", ".join(missing) + "."
        return True, ""

    @staticmethod
    def _validate_constraint(constraint: dict, parameter_ids: set[str]) -> tuple[bool, str]:
        required = ("id", "name", "description", "parameterId", "operator", "scope")
        missing = [field for field in required if not str(constraint.get(field, "")).strip()]
        if missing:
            return False, "Constraint is missing: " + ", ".join(missing) + "."
        if constraint["parameterId"] not in parameter_ids:
            return False, "Constraint references an unknown parameter."
        if constraint["operator"] not in CONSTRAINT_OPERATORS:
            return False, "Unsupported constraint operator."
        if constraint["scope"] not in CONSTRAINT_SCOPES:
            return False, "Constraint scope must be LOCAL or HIERARCHY."
        if constraint["operator"] == "RANGE":
            if constraint.get("lowerValue") in (None, "") or constraint.get("upperValue") in (None, ""):
                return False, "A RANGE constraint requires lowerValue and upperValue."
        elif constraint.get("value") in (None, ""):
            return False, "This constraint operator requires a value."
        aggregation = constraint.get("aggregation")
        if constraint["scope"] == "HIERARCHY" and not aggregation:
            return False, "A hierarchy constraint requires an aggregation rule."
        if aggregation and aggregation not in AGGREGATION_RULES:
            return False, "Unsupported aggregation rule."
        if aggregation == "CUSTOM" and not str(constraint.get("customAggregation", "")).strip():
            return False, "A CUSTOM aggregation requires a rule description."
        return True, ""

    def add_node(
        self,
        node_type: str,
        name: str,
        description: str = "",
        *,
        parameters: list[dict] | None = None,
        constraints: list[dict] | None = None,
        node_id: str | None = None,
        **attributes,
    ) -> tuple[bool, str, str]:
        if node_type not in NODE_TYPES:
            return False, "", "Unsupported persistent OA concept."
        valid_name, error = validate_concept_name(node_type, name)
        if not valid_name:
            return False, "", error
        if not description.strip():
            return False, "", "A core description is required."
        duplicate = self.find_duplicate(node_type, name)
        if duplicate:
            return False, duplicate, f"'{name}' is already in the model."

        parameters = copy.deepcopy(parameters or [])
        constraints = copy.deepcopy(constraints or [])
        parameter_ids = set()
        for parameter in parameters:
            ok, error = self._validate_parameter(parameter)
            if not ok:
                return False, "", error
            if parameter["id"] in parameter_ids:
                return False, "", "Parameter IDs must be unique within an element."
            parameter_ids.add(parameter["id"])
        for constraint in constraints:
            ok, error = self._validate_constraint(constraint, parameter_ids)
            if not ok:
                return False, "", error

        node_id = node_id or _new_uuid()
        if node_id in self.graph:
            return False, node_id, "The stable ID is already in use."

        guidance = CONCEPT_GUIDANCE[node_type]
        now = datetime.now(timezone.utc).isoformat()
        node_attributes = {
            "id": node_id,
            "sid": attributes.pop("sid", node_id),
            "type": node_type,
            "capella_type": guidance["capella_type"],
            "name": re.sub(r"\s+", " ", name.strip()),
            "description": re.sub(r"\s+", " ", description.strip()),
            "summary": attributes.pop("summary", ""),
            "status": attributes.pop("status", "DRAFT"),
            "review": attributes.pop("review", ""),
            "parameters": parameters,
            "constraints": constraints,
            "ontology_definition": guidance["definition"],
            "ontology_example": guidance["example"],
            "created_at": attributes.pop("created_at", now),
            "updated_at": now,
        }
        node_attributes.update(attributes)
        self._checkpoint()
        self.graph.add_node(node_id, **node_attributes)
        return True, node_id, ""

    def update_node(self, node_id: str, **changes) -> tuple[bool, str]:
        """Validate a complete edit preview before replacing the saved values."""
        if node_id not in self.graph:
            return False, "Element not found."
        current = copy.deepcopy(dict(self.graph.nodes[node_id]))
        for protected in ("id", "sid", "type", "capella_type"):
            if protected in changes and changes[protected] != current.get(protected):
                return False, f"'{protected}' is stable and cannot be changed by an edit."
        candidate = {**current, **changes}
        node_type = candidate["type"]
        ok, error = validate_concept_name(node_type, str(candidate.get("name", "")))
        if not ok:
            return False, error
        if not str(candidate.get("description", "")).strip():
            return False, "A core description is required."
        duplicate = self.find_duplicate(node_type, candidate["name"], exclude_id=node_id)
        if duplicate:
            return False, f"'{candidate['name']}' is already in the model."

        parameters = candidate.get("parameters", [])
        parameter_ids = set()
        for parameter in parameters:
            ok, error = self._validate_parameter(parameter)
            if not ok:
                return False, error
            parameter_ids.add(parameter["id"])
        for constraint in candidate.get("constraints", []):
            ok, error = self._validate_constraint(constraint, parameter_ids)
            if not ok:
                return False, error

        candidate["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._checkpoint()
        self.graph.nodes[node_id].clear()
        self.graph.nodes[node_id].update(candidate)
        return True, ""

    def update_node_attributes(self, node_id: str, **attributes) -> bool:
        ok, _ = self.update_node(node_id, **attributes)
        return ok

    def _relation_graph(self, relation: str) -> nx.DiGraph:
        result = nx.DiGraph()
        for source, target, data in self.graph.edges(data=True):
            if data.get("type") == relation:
                result.add_edge(source, target)
        return result

    def _would_create_cycle(self, source_id: str, target_id: str, relation: str) -> bool:
        if source_id == target_id:
            return True
        graph = self._relation_graph(relation)
        if target_id not in graph or source_id not in graph:
            return False
        return nx.has_path(graph, target_id, source_id)

    def has_relation(self, source_id: str, relation: str, target_id: str) -> bool:
        if source_id not in self.graph or target_id not in self.graph:
            return False
        return any(
            target == target_id and data.get("type") == relation
            for _, target, data in self.graph.out_edges(source_id, data=True)
        )

    def relation_targets(self, source_id: str, relation: str) -> list[str]:
        return [
            target
            for _, target, data in self.graph.out_edges(source_id, data=True)
            if data.get("type") == relation
        ]

    def relation_sources(self, target_id: str, relation: str) -> list[str]:
        return [
            source
            for source, _, data in self.graph.in_edges(target_id, data=True)
            if data.get("type") == relation
        ]

    def composition_parent(self, node_id: str) -> tuple[str, str] | None:
        for source, _, data in self.graph.in_edges(node_id, data=True):
            relation = data.get("type")
            if relation in COMPOSITION_RELATIONS:
                return source, relation
        return None

    def structural_parent(self, node_id: str) -> str | None:
        parent = self.composition_parent(node_id)
        return parent[0] if parent and parent[1] == "CONTAINS" else None

    def locations_for(self, node_id: str) -> list[str]:
        return self.relation_targets(node_id, "LOCATED_IN")

    def add_relation(
        self,
        source_id: str,
        relation: str,
        target_id: str,
        **attributes,
    ) -> tuple[bool, str]:
        if source_id not in self.graph or target_id not in self.graph:
            return False, "Both model elements must already exist."
        signature = (
            self.graph.nodes[source_id]["type"],
            relation,
            self.graph.nodes[target_id]["type"],
        )
        if signature not in ALLOWED_RELATIONS:
            return False, "That relationship is not allowed by the OA ontology."
        if source_id == target_id and relation in COMPOSITION_RELATIONS | {"LOCATED_IN"}:
            return False, "An element cannot compose, refine, or locate itself."
        if self.has_relation(source_id, relation, target_id):
            return False, "That relationship already exists."
        if relation in COMPOSITION_RELATIONS:
            if self.composition_parent(target_id):
                return False, "The child already has a composition/refinement parent."
            if self._would_create_cycle(source_id, target_id, relation):
                return False, "That relationship would create a composition cycle."
        if relation == "LOCATED_IN" and self._would_create_cycle(source_id, target_id, relation):
            return False, "That relationship would create a location cycle."
        if relation in ENDPOINT_RELATIONS and self.relation_targets(source_id, relation):
            return False, f"{relation} already has an endpoint."

        guidance = RELATION_GUIDANCE[relation]
        self._checkpoint()
        self.graph.add_edge(
            source_id,
            target_id,
            type=relation,
            ontology_definition=guidance["definition"],
            ontology_example=guidance["example"],
            confirmed_by="user",
            **attributes,
        )
        return True, ""

    def connected_relations(self, node_id: str) -> list[tuple[str, str, str]]:
        result = []
        for source, target, data in self.graph.edges(data=True):
            if source == node_id or target == node_id:
                result.append((source, str(data.get("type", "")), target))
        return result

    def remove_relation(
        self,
        source_id: str,
        relation: str,
        target_id: str,
    ) -> tuple[bool, str]:
        if source_id not in self.graph or target_id not in self.graph:
            return False, "Both model elements must already exist."
        matching_keys = [
            key
            for _, existing_target, key, data in self.graph.out_edges(
                source_id,
                keys=True,
                data=True,
            )
            if existing_target == target_id and data.get("type") == relation
        ]
        if not matching_keys:
            return False, "Relationship not found."
        self._checkpoint()
        for key in matching_keys:
            self.graph.remove_edge(source_id, target_id, key=key)
        return True, ""

    def remove_node(self, node_id: str, *, cascade_confirmed: bool = False) -> tuple[bool, str]:
        if node_id not in self.graph:
            return False, "Element not found."
        links = self.connected_relations(node_id)
        if links and not cascade_confirmed:
            return False, "Deletion requires confirmation because relationships are attached."
        self._checkpoint()
        self.graph.remove_node(node_id)
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
        return self.participants()

    def context_entities(self) -> list[str]:
        return self.nodes_of_type("OperationalEntity")

    def name(self, node_id: str) -> str:
        return str(self.graph.nodes[node_id].get("name", node_id))

    def participant_label(self, node_id: str) -> str:
        return f"{self.name(node_id)} [{self.graph.nodes[node_id]['type']}]"

    def participants_for_activity(self, activity_id: str) -> list[str]:
        return self.relation_sources(activity_id, "PERFORMS")

    def participant_for_activity(self, activity_id: str) -> str | None:
        performers = self.participants_for_activity(activity_id)
        return performers[0] if performers else None

    def actions_for_participant(self, participant_id: str) -> list[str]:
        return self.relation_targets(participant_id, "PERFORMS")

    def exchanges(self) -> list[str]:
        return self.nodes_of_type("OperationalExchange")

    def communication_means(self) -> list[str]:
        return self.nodes_of_type("CommunicationMean")

    def short_context(self, limit: int = 14) -> str:
        items = [
            f"{data.get('name')} ({data.get('type')})"
            for _, data in list(self.graph.nodes(data=True))[:limit]
        ]
        return ", ".join(items) if items else "No model elements yet."

    def friendly_show(self) -> str:
        lines = ["MODEL SO FAR", "=" * 64]
        order = (
            "OperationalCapability", "OperationalActor", "OperationalEntity",
            "OperationalActivity", "OperationalExchange", "CommunicationMean",
        )
        for node_type in order:
            lines.append(f"\n{CONCEPT_GUIDANCE[node_type]['friendly_name'].title()}s")
            nodes = self.nodes_of_type(node_type)
            if not nodes:
                lines.append("  (none)")
                continue
            for node_id in nodes:
                data = self.graph.nodes[node_id]
                lines.append(f"  - {data['name']} [{node_id[:8]}]")
                lines.append(f"      {data['description']}")
                if data.get("parameters"):
                    lines.append(f"      parameters: {len(data['parameters'])}")
                if data.get("constraints"):
                    lines.append(f"      constraints: {len(data['constraints'])}")

        lines.append("\nRelationships")
        edges = list(self.graph.edges(data=True))
        if not edges:
            lines.append("  (none)")
        else:
            for source, target, data in edges:
                lines.append(
                    f"  - {self.name(source)} --{data['type']}--> {self.name(target)}"
                )
        lines.extend([
            "",
            f"Elements: {self.graph.number_of_nodes()} | Relationships: {self.graph.number_of_edges()}",
            "=" * 64,
        ])
        return "\n".join(lines)

    def completeness_messages(self) -> list[str]:
        messages: list[str] = []
        for required, text in (
            ("OperationalCapability", "No operational capability has been created."),
            ("OperationalActivity", "No operational activity has been created."),
        ):
            if not self.nodes_of_type(required):
                messages.append(text)
        if not self.participants():
            messages.append("No operational actor or entity has been created.")

        for node_id, data in self.graph.nodes(data=True):
            if not str(data.get("description", "")).strip():
                messages.append(f"'{self.name(node_id)}' has no core description.")
            node_type = data.get("type")
            if node_type == "OperationalActivity" and not self.participants_for_activity(node_id):
                messages.append(f"'{self.name(node_id)}' has no performer.")
            elif node_type == "OperationalExchange":
                if not self.relation_targets(node_id, "SOURCE_ACTIVITY"):
                    messages.append(f"'{self.name(node_id)}' has no source activity.")
                if not self.relation_targets(node_id, "TARGET_ACTIVITY"):
                    messages.append(f"'{self.name(node_id)}' has no target activity.")
            elif node_type == "CommunicationMean":
                if not self.relation_targets(node_id, "SOURCE_PARTICIPANT"):
                    messages.append(f"'{self.name(node_id)}' has no source participant.")
                if not self.relation_targets(node_id, "TARGET_PARTICIPANT"):
                    messages.append(f"'{self.name(node_id)}' has no target participant.")
        return messages

    def to_document(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "model_type": "Arcadia Operational Analysis",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "capella_compatibility": {
                "stable_ids": True,
                "concept_mapping": "capella_type on every element",
                "loss_policy": "preserve user descriptions, parameters, constraints, and links",
            },
            "ontology": ontology_catalog(),
            "graph": json_graph.node_link_data(self.graph, edges="edges"),
        }

    def save(self, path: str) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.to_document(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return output

    def load(self, path: str) -> Path:
        source = Path(path)
        document = json.loads(source.read_text(encoding="utf-8"))
        graph_data = document.get("graph", document)
        loaded = json_graph.node_link_graph(graph_data, edges="edges", directed=True, multigraph=True)
        if not isinstance(loaded, nx.MultiDiGraph):
            loaded = nx.MultiDiGraph(loaded)
        self._checkpoint()
        self.graph = loaded
        self.graph.graph["schema_version"] = document.get("schema_version", 1)
        return source
