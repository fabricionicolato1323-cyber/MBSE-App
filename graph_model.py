from __future__ import annotations

import copy
import re

import graph_model_base as _base
from graph_model_base import *  # noqa: F401,F403 - preserve public API
from graph_model_base import OAGraph as _BaseOAGraph


def _characteristic_key(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


class OAGraph(_BaseOAGraph):
    """Persistent graph plus deterministic characteristic edit/remove helpers."""

    @classmethod
    def _validate_characteristics(
        cls,
        parameters: object,
        constraints: object,
    ) -> tuple[bool, str]:
        ok, error = super()._validate_characteristics(parameters, constraints)
        if not ok:
            return ok, error
        assert isinstance(parameters, list)
        seen: set[str] = set()
        for parameter in parameters:
            name = _characteristic_key(parameter.get("name", ""))
            if name in seen:
                return False, "Characteristic names must be unique within an element."
            seen.add(name)
        return True, ""

    def characteristic_name_exists(
        self,
        node_id: str,
        name: str,
        *,
        exclude_parameter_id: str | None = None,
    ) -> bool:
        if node_id not in self.graph:
            return False
        wanted = _characteristic_key(name)
        for parameter in self.graph.nodes[node_id].get("parameters", []):
            if not isinstance(parameter, dict):
                continue
            if str(parameter.get("id", "")) == str(exclude_parameter_id or ""):
                continue
            if _characteristic_key(parameter.get("name", "")) == wanted:
                return True
        return False

    def characteristic_records(self, node_id: str) -> list[tuple[dict, list[dict]]]:
        if node_id not in self.graph:
            return []
        data = self.graph.nodes[node_id]
        parameters = data.get("parameters", [])
        constraints = data.get("constraints", [])
        if not isinstance(parameters, list) or not isinstance(constraints, list):
            return []
        records: list[tuple[dict, list[dict]]] = []
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            parameter_id = str(parameter.get("id", ""))
            linked = [
                constraint
                for constraint in constraints
                if isinstance(constraint, dict)
                and str(constraint.get("parameterId", "")) == parameter_id
            ]
            records.append((copy.deepcopy(parameter), copy.deepcopy(linked)))
        return records

    def get_characteristic(
        self,
        node_id: str,
        parameter_id: str,
    ) -> tuple[dict, dict] | None:
        for parameter, constraints in self.characteristic_records(node_id):
            if str(parameter.get("id", "")) != str(parameter_id):
                continue
            if len(constraints) != 1:
                return None
            return parameter, constraints[0]
        return None

    def replace_characteristic(
        self,
        node_id: str,
        parameter_id: str,
        parameter: dict,
        constraint: dict,
    ) -> tuple[bool, str]:
        if node_id not in self.graph:
            return False, "Element not found."
        data = self.graph.nodes[node_id]
        parameters = copy.deepcopy(list(data.get("parameters", [])))
        constraints = copy.deepcopy(list(data.get("constraints", [])))

        parameter_index = next(
            (
                index
                for index, item in enumerate(parameters)
                if isinstance(item, dict)
                and str(item.get("id", "")) == str(parameter_id)
            ),
            None,
        )
        if parameter_index is None:
            return False, "Measurable characteristic not found."

        linked_indexes = [
            index
            for index, item in enumerate(constraints)
            if isinstance(item, dict)
            and str(item.get("parameterId", "")) == str(parameter_id)
        ]
        if len(linked_indexes) != 1:
            return False, "This characteristic does not have exactly one editable limitation."

        old_parameter = parameters[parameter_index]
        old_constraint = constraints[linked_indexes[0]]
        replacement_parameter = copy.deepcopy(parameter)
        replacement_constraint = copy.deepcopy(constraint)
        replacement_parameter["id"] = old_parameter["id"]
        replacement_constraint["id"] = old_constraint["id"]
        replacement_constraint["parameterId"] = old_parameter["id"]

        if self.characteristic_name_exists(
            node_id,
            str(replacement_parameter.get("name", "")),
            exclude_parameter_id=str(parameter_id),
        ):
            return False, "A measurable characteristic with that name already exists."

        parameters[parameter_index] = replacement_parameter
        constraints[linked_indexes[0]] = replacement_constraint
        return self.update_node(
            node_id,
            parameters=parameters,
            constraints=constraints,
        )

    def remove_characteristic(
        self,
        node_id: str,
        parameter_id: str,
    ) -> tuple[bool, str]:
        if node_id not in self.graph:
            return False, "Element not found."
        data = self.graph.nodes[node_id]
        parameters = copy.deepcopy(list(data.get("parameters", [])))
        constraints = copy.deepcopy(list(data.get("constraints", [])))
        remaining_parameters = [
            item
            for item in parameters
            if not (
                isinstance(item, dict)
                and str(item.get("id", "")) == str(parameter_id)
            )
        ]
        if len(remaining_parameters) == len(parameters):
            return False, "Measurable characteristic not found."
        remaining_constraints = [
            item
            for item in constraints
            if not (
                isinstance(item, dict)
                and str(item.get("parameterId", "")) == str(parameter_id)
            )
        ]
        return self.update_node(
            node_id,
            parameters=remaining_parameters,
            constraints=remaining_constraints,
        )
