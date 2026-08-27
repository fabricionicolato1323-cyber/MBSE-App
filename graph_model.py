from __future__ import annotations

import math
import re
from typing import Any

from graph_model_base import OAGraph as _BaseOAGraph


CHARACTERISTIC_VALUE_TYPES = {"number", "range", "text"}
CHARACTERISTIC_NODE_TYPES = {
    "OperationalCapability",
    "OperationalActor",
    "OperationalEntity",
    "OperationalActivity",
}


def _canonical(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def _coerce_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        if not math.isfinite(number):
            return None
        if number.is_integer() and re.fullmatch(r"[+-]?\d+(?:[.,]0+)?", value.strip()):
            return int(number)
        return number
    return None


class OAGraph(_BaseOAGraph):
    """Extend the existing OA graph with generic user-owned characteristics.

    Characteristics remain attributes of model elements/interaction edges. They are
    intentionally not promoted to graph nodes in this feature.
    """

    @staticmethod
    def _normalize_characteristic(characteristic: dict) -> tuple[bool, dict, str]:
        if not isinstance(characteristic, dict):
            return False, {}, "A characteristic must be a structured value."

        name = re.sub(r"\s+", " ", str(characteristic.get("name", "")).strip())
        if not name:
            return False, {}, "Characteristic name cannot be empty."
        if len(name) > 80:
            return False, {}, "Characteristic name is too long."

        value_type = str(characteristic.get("value_type", "")).strip().casefold()
        if value_type not in CHARACTERISTIC_VALUE_TYPES:
            return False, {}, "Unsupported characteristic value type."

        unit = re.sub(r"\s+", " ", str(characteristic.get("unit", "")).strip())
        normalized: dict[str, Any] = {
            "name": name,
            "value_type": value_type,
        }

        if value_type == "number":
            value = _coerce_number(characteristic.get("value"))
            if value is None:
                return False, {}, "Single numeric value must be a finite number."
            normalized["value"] = value
            normalized["unit"] = unit

        elif value_type == "range":
            lower = _coerce_number(characteristic.get("lower_bound"))
            upper = _coerce_number(characteristic.get("upper_bound"))
            if lower is None or upper is None:
                return False, {}, "Range bounds must be finite numbers."
            if lower > upper:
                return False, {}, "Lower bound cannot be greater than upper bound."
            normalized["lower_bound"] = lower
            normalized["upper_bound"] = upper
            normalized["unit"] = unit

        else:
            value = re.sub(r"\s+", " ", str(characteristic.get("value", "")).strip())
            if not value:
                return False, {}, "Text value cannot be empty."
            normalized["value"] = value

        return True, normalized, ""

    @staticmethod
    def _characteristic_duplicate(characteristics: list[dict], name: str) -> bool:
        wanted = _canonical(name)
        return any(_canonical(item.get("name", "")) == wanted for item in characteristics)

    def characteristics_for_node(self, node_id: str) -> list[dict]:
        if node_id not in self.graph:
            return []
        values = self.graph.nodes[node_id].get("characteristics", [])
        return list(values) if isinstance(values, list) else []

    def add_characteristic(self, node_id: str, characteristic: dict) -> tuple[bool, str]:
        if node_id not in self.graph:
            return False, "Model item does not exist."
        if self.graph.nodes[node_id].get("type") not in CHARACTERISTIC_NODE_TYPES:
            return False, "Characteristics are not supported for that model item."

        ok, normalized, error = self._normalize_characteristic(characteristic)
        if not ok:
            return False, error

        current = self.characteristics_for_node(node_id)
        if self._characteristic_duplicate(current, normalized["name"]):
            return False, "A characteristic with that name already exists for this item."

        self._checkpoint()
        self.graph.nodes[node_id]["characteristics"] = [*current, normalized]
        return True, ""

    def exchange_records(self) -> list[tuple[str, str, Any, str]]:
        result: list[tuple[str, str, Any, str]] = []
        for source, target, key, data in self.graph.edges(keys=True, data=True):
            if data.get("type") == "OPERATIONAL_EXCHANGE":
                result.append((source, target, key, data.get("name", "Interaction")))
        return result

    def characteristics_for_exchange(self, source_id: str, target_id: str, edge_key: Any) -> list[dict]:
        try:
            data = self.graph[source_id][target_id][edge_key]
        except (KeyError, TypeError):
            return []
        if data.get("type") != "OPERATIONAL_EXCHANGE":
            return []
        values = data.get("characteristics", [])
        return list(values) if isinstance(values, list) else []

    def add_exchange_characteristic(
        self,
        source_id: str,
        target_id: str,
        edge_key: Any,
        characteristic: dict,
    ) -> tuple[bool, str]:
        try:
            data = self.graph[source_id][target_id][edge_key]
        except (KeyError, TypeError):
            return False, "Interaction does not exist."
        if data.get("type") != "OPERATIONAL_EXCHANGE":
            return False, "That connection is not an interaction."

        ok, normalized, error = self._normalize_characteristic(characteristic)
        if not ok:
            return False, error

        current = self.characteristics_for_exchange(source_id, target_id, edge_key)
        if self._characteristic_duplicate(current, normalized["name"]):
            return False, "A characteristic with that name already exists for this interaction."

        self._checkpoint()
        data["characteristics"] = [*current, normalized]
        return True, ""

    @staticmethod
    def _format_characteristic(characteristic: dict) -> str:
        name = characteristic.get("name", "Characteristic")
        kind = characteristic.get("value_type")
        if kind == "range":
            value = f"{characteristic.get('lower_bound')} .. {characteristic.get('upper_bound')}"
            unit = characteristic.get("unit", "")
        else:
            value = str(characteristic.get("value", ""))
            unit = characteristic.get("unit", "") if kind == "number" else ""
        return f"{name}: {value}{(' ' + unit) if unit else ''}"

    def _characteristic_lines(self) -> list[str]:
        lines: list[str] = []
        type_labels = {
            "OperationalCapability": "Goal",
            "OperationalActor": "Participant",
            "OperationalEntity": "Participant / context",
            "OperationalActivity": "Action",
        }

        for node_id, data in self.graph.nodes(data=True):
            characteristics = self.characteristics_for_node(node_id)
            if not characteristics:
                continue
            label = type_labels.get(data.get("type"), "Item")
            lines.append(f"  {label}: {self.name(node_id)}")
            for item in characteristics:
                lines.append(f"    - {self._format_characteristic(item)}")

        for source, target, key, name in self.exchange_records():
            characteristics = self.characteristics_for_exchange(source, target, key)
            if not characteristics:
                continue
            lines.append(
                f"  Interaction: {name} ({self.name(source)} -> {self.name(target)})"
            )
            for item in characteristics:
                lines.append(f"    - {self._format_characteristic(item)}")
        return lines

    def characteristic_issues(self) -> list[str]:
        issues: list[str] = []

        def inspect(owner_label: str, values: Any) -> None:
            if values is None:
                return
            if not isinstance(values, list):
                issues.append(f"{owner_label} has malformed characteristics data.")
                return
            seen: set[str] = set()
            for item in values:
                ok, normalized, error = self._normalize_characteristic(item)
                if not ok:
                    issues.append(f"{owner_label} has an invalid characteristic: {error}")
                    continue
                key = _canonical(normalized["name"])
                if key in seen:
                    issues.append(
                        f"{owner_label} has duplicate characteristic '{normalized['name']}'."
                    )
                seen.add(key)

        for node_id, data in self.graph.nodes(data=True):
            inspect(f"'{self.name(node_id)}'", data.get("characteristics"))
        for source, target, key, name in self.exchange_records():
            data = self.graph[source][target][key]
            inspect(f"interaction '{name}'", data.get("characteristics"))
        return issues

    def completeness_messages(self) -> list[str]:
        return [*super().completeness_messages(), *self.characteristic_issues()]

    def friendly_show(self) -> str:
        base = super().friendly_show().rstrip()
        details = self._characteristic_lines()
        if not details:
            return base
        return "\n".join(
            [
                base,
                "",
                "Characteristics",
                "-" * 64,
                *details,
            ]
        )
