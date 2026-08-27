"""Persistent NetworkX model and deterministic write barrier for OA."""

from __future__ import annotations

import copy
import json
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

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
NODE_KEY_FIELD = "nodeKey"

_QUANTITY_KIND_UNITS = {
    "length": {
        "m", "meter", "meters", "metre", "metres", "km", "kilometer",
        "kilometers", "kilometre", "kilometres", "cm", "mm", "ft", "feet",
        "mi", "mile", "miles", "nm", "nauticalmile", "nauticalmiles",
    },
    "area": {
        "m2", "m²", "sqm", "squaremeter", "squaremeters", "squaremetre",
        "squaremetres", "km2", "km²", "sqkm", "squarekilometer",
        "squarekilometers", "squarekilometre", "squarekilometres", "ha",
        "hectare", "hectares",
    },
    "duration": {
        "ms", "millisecond", "milliseconds", "s", "sec", "second",
        "seconds", "min", "minute", "minutes", "h", "hr", "hour", "hours",
        "day", "days",
    },
    "count": {
        "1", "count", "counts", "item", "items", "person", "people",
        "unit", "units", "vehicle", "vehicles",
    },
    "speed": {
        "m/s", "mps", "km/h", "kmh", "kph", "mph", "kt", "kts", "knot",
        "knots",
    },
    "percentage": {"%", "percent", "percentage"},
}
_QUANTITY_KIND_ALIASES = {
    "time": "duration",
    "ratio": "percentage",
}
_MEASUREMENT_TERM_SUGGESTIONS = {
    "altitude": "length",
    "depth": "length",
    "distance": "length",
    "height": "length",
    "radius": "length",
    "range": "length",
    "width": "length",
}


class ModelLoadError(ValueError):
    """Raised when a saved model cannot pass the deterministic load barrier."""


@dataclass(frozen=True)
class LoadPlan:
    source: Path
    graph: nx.MultiDiGraph
    source_schema_version: int
    migration_summary: tuple[str, ...] = ()

    @property
    def requires_confirmation(self) -> bool:
        return self.source_schema_version < SCHEMA_VERSION


class MigrationConfirmationRequired(ModelLoadError):
    def __init__(self, plan: LoadPlan) -> None:
        super().__init__("The saved model requires confirmed migration before loading.")
        self.plan = plan


def _canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _normalized_unit(value: object) -> str:
    return re.sub(r"[\s_-]+", "", str(value).strip().casefold())


def _decimal_value(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def validate_custom_aggregation_rule(value: str) -> tuple[bool, str]:
    """Require a short, explicit rule rather than a placeholder token."""
    normalized = re.sub(r"\s+", " ", value.strip())
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", normalized)
    distinct = {character.casefold() for character in normalized if character.isalnum()}
    if len(words) < 2 or len(distinct) < 3:
        return False, (
            "Describe how child values are combined using at least two meaningful words."
        )
    return True, ""


def _node_link_data(graph: nx.MultiDiGraph) -> dict:
    """Serialize with the configured edge key across supported NetworkX 3.x APIs."""
    try:
        return json_graph.node_link_data(
            graph,
            edges="edges",
            name=NODE_KEY_FIELD,
        )
    except TypeError as exc:
        if "unexpected keyword argument 'edges'" not in str(exc):
            raise
        return json_graph.node_link_data(
            graph,
            link="edges",
            name=NODE_KEY_FIELD,
        )


def _node_link_graph(graph_data: dict, node_key_field: str) -> nx.MultiDiGraph:
    """Deserialize NetworkX node-link data across supported NetworkX 3.x APIs."""
    try:
        return json_graph.node_link_graph(
            graph_data,
            edges="edges",
            name=node_key_field,
            directed=True,
            multigraph=True,
        )
    except TypeError as exc:
        if "unexpected keyword argument 'edges'" not in str(exc):
            raise
        return json_graph.node_link_graph(
            graph_data,
            link="edges",
            name=node_key_field,
            directed=True,
            multigraph=True,
        )


class OAGraph:
    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph(
            model="Arcadia Operational Analysis",
            schema_version=SCHEMA_VERSION,
        )
        self._history: list[nx.MultiDiGraph] = []
        self._action_depth = 0
        self._action_snapshot: nx.MultiDiGraph | None = None
        self._action_dirty = False
        self.last_undo_description = ""

    def _append_history(self, snapshot: nx.MultiDiGraph) -> None:
        self._history.append(snapshot)
        if len(self._history) > 100:
            self._history.pop(0)

    def _checkpoint(self) -> None:
        if self._action_depth:
            self._action_dirty = True
            return
        self._append_history(copy.deepcopy(self.graph))

    @contextmanager
    def user_action(self) -> Iterator[None]:
        """Group multiple validated mutations into one atomic undo boundary."""
        outermost = self._action_depth == 0
        if outermost:
            self._action_snapshot = copy.deepcopy(self.graph)
            self._action_dirty = False
        self._action_depth += 1
        try:
            yield
        except Exception:
            self._action_depth -= 1
            if outermost:
                assert self._action_snapshot is not None
                self.graph = self._action_snapshot
                self._action_snapshot = None
                self._action_dirty = False
            raise
        else:
            self._action_depth -= 1
            if outermost:
                snapshot = self._action_snapshot
                dirty = self._action_dirty
                self._action_snapshot = None
                self._action_dirty = False
                if dirty and snapshot is not None and not nx.utils.graphs_equal(snapshot, self.graph):
                    self._append_history(snapshot)

    @staticmethod
    def _edge_facts(graph: nx.MultiDiGraph) -> set[tuple[str, str, str]]:
        return {
            (str(source), str(data.get("type", "")), str(target))
            for source, target, data in graph.edges(data=True)
        }

    @staticmethod
    def _graph_name(graph: nx.MultiDiGraph, node_id: str) -> str:
        if node_id not in graph:
            return node_id
        return str(graph.nodes[node_id].get("name", node_id))

    @classmethod
    def _describe_action(
        cls,
        before: nx.MultiDiGraph,
        after: nx.MultiDiGraph,
    ) -> str:
        """Describe the user-level graph action represented by two snapshots."""
        before_nodes = set(before.nodes)
        after_nodes = set(after.nodes)
        added_nodes = sorted(after_nodes - before_nodes)
        removed_nodes = sorted(before_nodes - after_nodes)
        before_edges = cls._edge_facts(before)
        after_edges = cls._edge_facts(after)
        added_edges = sorted(after_edges - before_edges)
        removed_edges = sorted(before_edges - after_edges)
        edited_nodes = sorted(
            node_id
            for node_id in before_nodes & after_nodes
            if dict(before.nodes[node_id]) != dict(after.nodes[node_id])
        )

        changes = (
            len(added_nodes)
            + len(removed_nodes)
            + len(added_edges)
            + len(removed_edges)
            + len(edited_nodes)
        )
        if changes == 1 and added_nodes:
            node_id = added_nodes[0]
            data = after.nodes[node_id]
            category = CONCEPT_GUIDANCE[str(data.get("type", ""))]["friendly_name"]
            return f"added element '{cls._graph_name(after, node_id)}' [{category}]"
        if changes == 1 and removed_nodes:
            node_id = removed_nodes[0]
            data = before.nodes[node_id]
            category = CONCEPT_GUIDANCE[str(data.get("type", ""))]["friendly_name"]
            return f"deleted element '{cls._graph_name(before, node_id)}' [{category}]"
        if changes == 1 and added_edges:
            source, relation, target = added_edges[0]
            relation_label = RELATION_GUIDANCE[relation]["friendly_name"]
            return (
                "added relationship "
                f"{cls._graph_name(after, source)} -- {relation_label} --> "
                f"{cls._graph_name(after, target)}"
            )
        if changes == 1 and removed_edges:
            source, relation, target = removed_edges[0]
            relation_label = RELATION_GUIDANCE[relation]["friendly_name"]
            return (
                "removed relationship "
                f"{cls._graph_name(before, source)} -- {relation_label} --> "
                f"{cls._graph_name(before, target)}"
            )
        if changes == 1 and edited_nodes:
            node_id = edited_nodes[0]
            return f"edited element '{cls._graph_name(after, node_id)}'"

        parts = []
        for count, singular in (
            (len(added_nodes), "element added"),
            (len(removed_nodes), "element deleted"),
            (len(added_edges), "relationship added"),
            (len(removed_edges), "relationship removed"),
            (len(edited_nodes), "element edited"),
        ):
            if count:
                label = singular if count == 1 else singular.replace("element", "elements").replace(
                    "relationship", "relationships"
                )
                parts.append(f"{count} {label}")
        return "compound graph action: " + ", ".join(parts) if parts else "graph action"

    def undo(self) -> bool:
        if self._action_depth:
            self.last_undo_description = ""
            return False
        if not self._history:
            self.last_undo_description = ""
            return False
        previous = self._history.pop()
        self.last_undo_description = self._describe_action(previous, self.graph)
        self.graph = previous
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

    @classmethod
    def _validate_characteristics(
        cls,
        parameters: object,
        constraints: object,
    ) -> tuple[bool, str]:
        if not isinstance(parameters, list):
            return False, "Element parameters must be a list."
        if not isinstance(constraints, list):
            return False, "Element constraints must be a list."
        parameter_ids: set[str] = set()
        for parameter in parameters:
            if not isinstance(parameter, dict):
                return False, "Every parameter must be an object."
            ok, error = cls._validate_parameter(parameter)
            if not ok:
                return False, error
            parameter_id = str(parameter["id"])
            if parameter_id in parameter_ids:
                return False, "Parameter IDs must be unique within an element."
            parameter_ids.add(parameter_id)
        constraint_ids: set[str] = set()
        for constraint in constraints:
            if not isinstance(constraint, dict):
                return False, "Every constraint must be an object."
            ok, error = cls._validate_constraint(constraint, parameter_ids)
            if not ok:
                return False, error
            constraint_id = str(constraint["id"])
            if constraint_id in constraint_ids:
                return False, "Constraint IDs must be unique within an element."
            constraint_ids.add(constraint_id)
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
            lower = _decimal_value(constraint.get("lowerValue"))
            upper = _decimal_value(constraint.get("upperValue"))
            if lower is None or upper is None:
                return False, "Constraint range values must be finite numbers."
            if lower > upper:
                return False, "A RANGE lower limit cannot be greater than its upper limit."
        elif constraint.get("value") in (None, ""):
            return False, "This constraint operator requires a value."
        elif _decimal_value(constraint.get("value")) is None:
            return False, "Constraint values must be finite numbers."
        aggregation = constraint.get("aggregation")
        if constraint["scope"] == "HIERARCHY" and not aggregation:
            return False, "A hierarchy constraint requires an aggregation rule."
        if aggregation and aggregation not in AGGREGATION_RULES:
            return False, "Unsupported aggregation rule."
        if aggregation == "CUSTOM":
            ok, error = validate_custom_aggregation_rule(
                str(constraint.get("customAggregation", ""))
            )
            if not ok:
                return False, f"A CUSTOM aggregation requires an explicit rule. {error}"
        return True, ""

    @staticmethod
    def characteristic_warnings(
        parameters: object,
        constraints: object,
    ) -> list[str]:
        """Return non-blocking semantic warnings without changing user values."""
        if not isinstance(parameters, list) or not isinstance(constraints, list):
            return []
        warnings: list[str] = []
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            name = str(parameter.get("name", "measurement"))
            raw_kind = str(parameter.get("quantityKind", "")).strip()
            kind = _canonical(raw_kind)
            canonical_kind = _QUANTITY_KIND_ALIASES.get(kind, kind)
            unit = str(parameter.get("unit", "")).strip()
            normalized_unit = _normalized_unit(unit)

            suggested_kind = _MEASUREMENT_TERM_SUGGESTIONS.get(kind)
            if suggested_kind:
                warnings.append(
                    f"'{name}': quantity kind '{raw_kind}' describes a measurement; "
                    f"use '{suggested_kind}' as the dimensional kind unless the supplied term is intentional."
                )
                canonical_kind = suggested_kind
            elif canonical_kind not in _QUANTITY_KIND_UNITS:
                warnings.append(
                    f"'{name}': quantity kind '{raw_kind}' is not in the recognized dimensional vocabulary; "
                    "verify it before approval."
                )
                continue

            if normalized_unit not in _QUANTITY_KIND_UNITS[canonical_kind]:
                warnings.append(
                    f"'{name}': unit '{unit}' may not match quantity kind '{canonical_kind}'."
                )
        return warnings

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
            return False, "", "Unsupported model category."
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
        ok, error = self._validate_characteristics(parameters, constraints)
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

        ok, error = self._validate_characteristics(
            candidate.get("parameters", []),
            candidate.get("constraints", []),
        )
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
            return False, "That relationship is not allowed by the model rules."
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
        node_type = str(self.graph.nodes[node_id]["type"])
        return f"{self.name(node_id)} [{CONCEPT_GUIDANCE[node_type]['friendly_name']}]"

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
            f"{data.get('name')} "
            f"({CONCEPT_GUIDANCE[str(data.get('type'))]['friendly_name']})"
            for _, data in list(self.graph.nodes(data=True))[:limit]
        ]
        return ", ".join(items) if items else "No model elements yet."

    @staticmethod
    def _constraint_summary(constraint: dict, unit: str) -> str:
        operator = str(constraint.get("operator", "")).upper()
        labels = {"MIN": "Minimum", "MAX": "Maximum", "EQUAL": "Exact value"}
        if operator == "RANGE":
            suffix = f" {unit}" if unit else ""
            return (
                f"Range — Lower limit: {constraint.get('lowerValue')}{suffix} | "
                f"Upper limit: {constraint.get('upperValue')}{suffix}"
            )
        value = str(constraint.get("value", ""))
        label = labels.get(operator, operator.title())
        suffix = f" {unit}" if unit else ""
        return f"{label}: {value}{suffix}".rstrip()

    @classmethod
    def _characteristic_lines(cls, data: dict, indent: str = "      ") -> list[str]:
        parameters = data.get("parameters", [])
        constraints = data.get("constraints", [])
        if not isinstance(parameters, list) or not isinstance(constraints, list):
            return []
        constraints_by_parameter: dict[str, list[dict]] = {}
        for constraint in constraints:
            if isinstance(constraint, dict):
                constraints_by_parameter.setdefault(str(constraint.get("parameterId", "")), []).append(
                    constraint
                )

        lines: list[str] = []
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            parameter_id = str(parameter.get("id", ""))
            name = str(parameter.get("name", "Unnamed measurement"))
            description = str(parameter.get("description", ""))
            quantity_kind = str(parameter.get("quantityKind", ""))
            unit = str(parameter.get("unit", ""))
            lines.append(f"{indent}Attribute: {name}")
            if description:
                lines.append(f"{indent}  Meaning: {description}")
            lines.append(f"{indent}  Quantity kind: {quantity_kind} | Unit: {unit}")
            for constraint in constraints_by_parameter.get(parameter_id, []):
                lines.append(f"{indent}  {cls._constraint_summary(constraint, unit)}")
                condition = str(constraint.get("applicableCondition", "")).strip()
                scope = str(constraint.get("scope", "LOCAL"))
                aggregation = str(constraint.get("aggregation", "")).strip()
                lines.append(f"{indent}  Scope: {scope}")
                if aggregation:
                    aggregation_text = aggregation
                    if aggregation == "CUSTOM":
                        aggregation_text += f" — {constraint.get('customAggregation', '')}"
                    lines.append(f"{indent}  Aggregation: {aggregation_text}")
                if condition:
                    lines.append(f"{indent}  Condition: {condition}")
        for warning in cls.characteristic_warnings(parameters, constraints):
            lines.append(f"{indent}Warning: {warning}")
        return lines

    def friendly_characteristics(self, node_id: str, indent: str = "") -> str:
        if node_id not in self.graph:
            return ""
        return "\n".join(self._characteristic_lines(dict(self.graph.nodes[node_id]), indent))

    def friendly_show(self) -> str:
        lines: list[str] = []
        order = (
            "OperationalCapability", "OperationalActor", "OperationalEntity",
            "OperationalActivity", "OperationalExchange", "CommunicationMean",
        )
        for node_type in order:
            if lines:
                lines.append("")
            lines.append(CONCEPT_GUIDANCE[node_type]["plural_name"].title())
            nodes = self.nodes_of_type(node_type)
            if not nodes:
                lines.append("  (none)")
                continue
            for node_id in nodes:
                data = self.graph.nodes[node_id]
                lines.append(f"  - {data['name']}")
                lines.append(f"      ID: {node_id}")
                sid = str(data.get("sid", "")).strip()
                if sid and sid != node_id:
                    lines.append(f"      SID: {sid}")
                lines.append(
                    f"      Category: {CONCEPT_GUIDANCE[node_type]['friendly_name'].title()}"
                )
                lines.append(f"      Description: {data['description']}")
                lines.append(f"      Status: {data.get('status', 'DRAFT')}")
                summary = str(data.get("summary", "")).strip()
                review = str(data.get("review", "")).strip()
                if summary:
                    lines.append(f"      Summary: {summary}")
                if review:
                    lines.append(f"      Review: {review}")
                actor_nature = str(data.get("actor_nature", "")).strip()
                if actor_nature:
                    actor_label = {
                        "HUMAN": "Human",
                        "NON_HUMAN": "Non-human (confirmed)",
                    }.get(actor_nature, actor_nature)
                    lines.append(f"      Participant nature: {actor_label}")
                if data.get("external_system_confirmed_by"):
                    lines.append(
                        "      External-system status: confirmed as an existing external participant"
                    )
                characteristic_lines = self._characteristic_lines(dict(data))
                if characteristic_lines:
                    lines.extend(characteristic_lines)
                else:
                    lines.append("      Attributes/limitations: none")

        lines.append("\nRelationships")
        edges = list(self.graph.edges(data=True))
        if not edges:
            lines.append("  (none)")
        else:
            for source, target, data in edges:
                relation = str(data["type"])
                lines.append(
                    f"  - {self.name(source)} [{source}] -- "
                    f"{RELATION_GUIDANCE[relation]['friendly_name']} --> "
                    f"{self.name(target)} [{target}]"
                )
        lines.extend([
            "",
            f"Elements: {self.graph.number_of_nodes()} | Relationships: {self.graph.number_of_edges()}",
        ])
        return "\n".join(lines)

    def completeness_messages(self) -> list[str]:
        messages: list[str] = []
        for required, text in (
            ("OperationalCapability", "No required outcome has been created."),
            ("OperationalActivity", "No activity has been created."),
        ):
            if not self.nodes_of_type(required):
                messages.append(text)
        if not self.participants():
            messages.append("No participant has been created.")

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
            for warning in self.characteristic_warnings(
                data.get("parameters", []),
                data.get("constraints", []),
            ):
                messages.append(f"'{self.name(node_id)}': {warning}")
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
            "graph": _node_link_data(self.graph),
        }

    def save(self, path: str) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.to_document(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return output

    @staticmethod
    def _uuid_is_valid(value: object) -> bool:
        try:
            uuid.UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            return False
        return True

    @classmethod
    def _validate_loaded_graph(cls, candidate: nx.MultiDiGraph) -> None:
        if not isinstance(candidate, nx.MultiDiGraph):
            raise ModelLoadError("The saved Project Graph must be a directed multigraph.")

        identity_values: set[str] = set()
        sid_values: set[str] = set()
        duplicate_names: set[tuple[str, str]] = set()
        for node_id, data in candidate.nodes(data=True):
            if not isinstance(node_id, str) or not node_id:
                raise ModelLoadError("Every graph key must be a non-empty UUID string.")
            if not isinstance(data, dict):
                raise ModelLoadError(f"Element '{node_id}' does not contain an attribute object.")
            canonical_id = data.get("id")
            if canonical_id != node_id:
                raise ModelLoadError(
                    f"Element '{node_id}' has a canonical id that does not match its graph key."
                )
            if not cls._uuid_is_valid(canonical_id):
                raise ModelLoadError(f"Element '{node_id}' does not use a valid UUID id.")
            if canonical_id in identity_values:
                raise ModelLoadError(f"Duplicate canonical id '{canonical_id}'.")
            identity_values.add(canonical_id)

            sid = data.get("sid")
            if sid not in (None, ""):
                if not isinstance(sid, str):
                    raise ModelLoadError(f"Element '{node_id}' has a non-text sid.")
                if sid in sid_values:
                    raise ModelLoadError(
                        f"Duplicate sid '{sid}'. Resolve the external aliases before loading."
                    )
                sid_values.add(sid)

            node_type = data.get("type")
            if node_type not in NODE_TYPES:
                raise ModelLoadError(
                    f"Element '{node_id}' uses unsupported Project Graph type '{node_type}'."
                )
            name = str(data.get("name", ""))
            valid_name, error = validate_concept_name(str(node_type), name)
            if not valid_name:
                raise ModelLoadError(f"Element '{node_id}' has an invalid name: {error}")
            if not str(data.get("description", "")).strip():
                raise ModelLoadError(f"Element '{node_id}' has no core description.")
            family = "OperationalParticipant" if node_type in PARTICIPANT_TYPES else str(node_type)
            name_key = (family, _canonical(name))
            if name_key in duplicate_names:
                raise ModelLoadError(
                    f"Duplicate name '{name}' exists in the '{family}' identity scope."
                )
            duplicate_names.add(name_key)

            guidance = CONCEPT_GUIDANCE[str(node_type)]
            if data.get("capella_type") != guidance["capella_type"]:
                raise ModelLoadError(
                    f"Element '{node_id}' has an invalid Capella concept mapping."
                )
            if not str(data.get("ontology_definition", "")).strip():
                raise ModelLoadError(f"Element '{node_id}' has no ontology definition.")
            if not str(data.get("ontology_example", "")).strip():
                raise ModelLoadError(f"Element '{node_id}' has no ontology example.")
            ok, error = cls._validate_characteristics(
                data.get("parameters", []),
                data.get("constraints", []),
            )
            if not ok:
                raise ModelLoadError(f"Element '{node_id}' is invalid: {error}")

        seen_relations: set[tuple[str, str, str]] = set()
        parent_for: dict[str, tuple[str, str]] = {}
        endpoint_for: set[tuple[str, str]] = set()
        relation_graphs = {
            relation: nx.DiGraph()
            for relation in COMPOSITION_RELATIONS | {"LOCATED_IN"}
        }
        for source, target, data in candidate.edges(data=True):
            if not isinstance(data, dict):
                raise ModelLoadError("Every relationship must contain an attribute object.")
            relation = data.get("type")
            signature = (
                candidate.nodes[source].get("type"),
                relation,
                candidate.nodes[target].get("type"),
            )
            if signature not in ALLOWED_RELATIONS:
                raise ModelLoadError(
                    f"Relationship '{source}' --{relation}--> '{target}' is not allowed."
                )
            relation_key = (str(source), str(relation), str(target))
            if relation_key in seen_relations:
                raise ModelLoadError(
                    f"Duplicate relationship '{source}' --{relation}--> '{target}'."
                )
            seen_relations.add(relation_key)
            if source == target and relation in COMPOSITION_RELATIONS | {"LOCATED_IN"}:
                raise ModelLoadError("An element cannot compose, refine, or locate itself.")
            if relation in COMPOSITION_RELATIONS:
                if target in parent_for:
                    existing_source, existing_relation = parent_for[str(target)]
                    raise ModelLoadError(
                        f"Element '{target}' has multiple parents: "
                        f"'{existing_source}' via {existing_relation} and '{source}' via {relation}."
                    )
                parent_for[str(target)] = (str(source), str(relation))
            if relation in ENDPOINT_RELATIONS:
                endpoint_key = (str(source), str(relation))
                if endpoint_key in endpoint_for:
                    raise ModelLoadError(f"Element '{source}' has more than one {relation} endpoint.")
                endpoint_for.add(endpoint_key)
            if relation in relation_graphs:
                relation_graphs[str(relation)].add_edge(source, target)
            if not str(data.get("ontology_definition", "")).strip():
                raise ModelLoadError(
                    f"Relationship '{source}' --{relation}--> '{target}' has no definition."
                )
            if not str(data.get("ontology_example", "")).strip():
                raise ModelLoadError(
                    f"Relationship '{source}' --{relation}--> '{target}' has no example."
                )

        for relation, relation_graph in relation_graphs.items():
            if not nx.is_directed_acyclic_graph(relation_graph):
                raise ModelLoadError(f"The loaded graph contains a {relation} cycle.")

    @staticmethod
    def _graph_data(document: dict) -> tuple[dict, str]:
        graph_data = document.get("graph", document)
        if not isinstance(graph_data, dict):
            raise ModelLoadError("The saved model does not contain a graph object.")
        nodes = graph_data.get("nodes", [])
        if not isinstance(nodes, list):
            raise ModelLoadError("The saved model graph has no valid nodes list.")
        node_key_field = (
            NODE_KEY_FIELD
            if any(isinstance(node, dict) and NODE_KEY_FIELD in node for node in nodes)
            else "id"
        )
        return graph_data, node_key_field

    @classmethod
    def prepare_load(cls, path: str) -> LoadPlan:
        source = Path(path)
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ModelLoadError(f"The model file could not be read: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ModelLoadError(
                f"The model file is not valid JSON at line {exc.lineno}, column {exc.colno}."
            ) from exc
        if not isinstance(document, dict):
            raise ModelLoadError("The saved model root must be a JSON object.")
        raw_version = document.get("schema_version", 1)
        if not isinstance(raw_version, int):
            raise ModelLoadError("schema_version must be an integer.")
        if raw_version not in {1, SCHEMA_VERSION}:
            raise ModelLoadError(
                f"Unsupported schema_version {raw_version}; supported versions are 1 and {SCHEMA_VERSION}."
            )

        graph_data, node_key_field = cls._graph_data(document)
        try:
            loaded = _node_link_graph(graph_data, node_key_field)
        except (KeyError, TypeError, ValueError, nx.NetworkXError) as exc:
            raise ModelLoadError(f"The saved graph structure is invalid: {exc}") from exc
        if not isinstance(loaded, nx.MultiDiGraph):
            loaded = nx.MultiDiGraph(loaded)

        missing_sid = 0
        restored_id = 0
        migrated_metadata = 0
        for node_id, data in loaded.nodes(data=True):
            if "id" not in data:
                data["id"] = node_id
                restored_id += 1
            node_type = data.get("type")
            if raw_version == 1 and node_type in NODE_TYPES:
                guidance = CONCEPT_GUIDANCE[str(node_type)]
                if not data.get("sid"):
                    data["sid"] = data["id"]
                    missing_sid += 1
                for key, value in (
                    ("capella_type", guidance["capella_type"]),
                    ("ontology_definition", guidance["definition"]),
                    ("ontology_example", guidance["example"]),
                    ("parameters", []),
                    ("constraints", []),
                ):
                    if key not in data:
                        data[key] = copy.deepcopy(value)
                        migrated_metadata += 1
        if raw_version == 1:
            for _, _, data in loaded.edges(data=True):
                relation = data.get("type")
                if relation in RELATION_GUIDANCE:
                    guidance = RELATION_GUIDANCE[str(relation)]
                    for key, value in (
                        ("ontology_definition", guidance["definition"]),
                        ("ontology_example", guidance["example"]),
                        ("confirmed_by", "user"),
                    ):
                        if key not in data:
                            data[key] = value
                            migrated_metadata += 1

        loaded.graph["model"] = loaded.graph.get("model", "Arcadia Operational Analysis")
        loaded.graph["schema_version"] = SCHEMA_VERSION
        cls._validate_loaded_graph(loaded)

        summary: list[str] = []
        if raw_version == 1:
            summary.append(f"Schema version 1 will be migrated to {SCHEMA_VERSION} in memory.")
            summary.append(f"Missing sid values set to canonical id: {missing_sid}.")
            summary.append(f"Missing ontology or model metadata restored: {migrated_metadata}.")
            if restored_id:
                summary.append(f"Canonical ids restored from graph keys: {restored_id}.")
            summary.append("The source file will remain unchanged until a later save.")
        return LoadPlan(source, loaded, raw_version, tuple(summary))

    def apply_load(self, plan: LoadPlan) -> Path:
        self._checkpoint()
        self.graph = copy.deepcopy(plan.graph)
        return plan.source

    def load(self, path: str, *, confirm_migration: bool = False) -> Path:
        plan = self.prepare_load(path)
        if plan.requires_confirmation and not confirm_migration:
            raise MigrationConfirmationRequired(plan)
        return self.apply_load(plan)
