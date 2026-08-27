from __future__ import annotations

import math
import re
from typing import Any


class CharacteristicsFlowMixin:
    """User-facing elicitation for generic model characteristics.

    The user supplies every name and value. No AI is asked to invent, infer, or
    complete characteristic values.
    """

    @staticmethod
    def _parse_number(raw: str) -> int | float | None:
        text = raw.strip().replace(",", ".")
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
        if not math.isfinite(value):
            return None
        if value.is_integer() and re.fullmatch(r"[+-]?\d+(?:\.0+)?", text):
            return int(value)
        return value

    def _ask_text(self, question: str, *, allow_empty: bool = False, max_length: int = 120) -> str:
        while True:
            self.draw_question(
                question,
                explanation=(
                    "Enter the value directly."
                    if not allow_empty
                    else "Enter a value, or press Enter if no value is needed."
                ),
                expected_structure="Short text",
            )
            value = input("> ").strip()
            if self.command(value):
                continue
            value = re.sub(r"\s+", " ", value)
            if not value and allow_empty:
                return ""
            if not value:
                self.add_notice("The answer cannot be empty.")
                continue
            if len(value) > max_length:
                self.add_notice("Please provide a shorter value.")
                continue
            return value

    def _ask_numeric(self, question: str) -> int | float:
        while True:
            self.draw_question(
                question,
                explanation="Enter a finite number.",
                expected_structure="Number",
            )
            raw = input("> ").strip()
            if self.command(raw):
                continue
            value = self._parse_number(raw)
            if value is not None:
                return value
            self.add_notice("Please enter a valid finite number.")

    def _ask_unit(self) -> str:
        return self._ask_text(
            "What is the unit?",
            allow_empty=True,
            max_length=40,
        )

    def _characteristic_targets(self) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        for node_id, data in self.model.graph.nodes(data=True):
            node_type = data.get("type")
            if node_type == "OperationalCapability":
                label = f"Goal: {self.model.name(node_id)}"
            elif node_type == "OperationalActivity":
                label = f"Action: {self.model.name(node_id)}"
            elif node_type == "OperationalActor":
                label = f"Participant: {self.model.name(node_id)}"
            elif node_type == "OperationalEntity":
                label = f"Participant / context: {self.model.name(node_id)}"
            else:
                continue
            targets.append({"kind": "node", "node_id": node_id, "label": label})

        for source, target, key, name in self.model.exchange_records():
            targets.append(
                {
                    "kind": "exchange",
                    "source": source,
                    "target": target,
                    "key": key,
                    "label": (
                        f"Interaction: {name} "
                        f"({self.model.name(source)} -> {self.model.name(target)})"
                    ),
                }
            )
        return targets

    def _build_characteristic(self) -> dict:
        name = self._ask_text("What is the characteristic name?", max_length=80)
        value_type = self.ask_choice(
            "What kind of value does it have?",
            [
                ("number", "Single numeric value"),
                ("range", "Numeric range"),
                ("text", "Text value"),
            ],
            "This keeps numeric values, ranges, and descriptive values structured.",
        )

        if value_type == "number":
            return {
                "name": name,
                "value_type": "number",
                "value": self._ask_numeric("What is the numeric value?"),
                "unit": self._ask_unit(),
            }

        if value_type == "range":
            lower = self._ask_numeric("What is the lower bound?")
            while True:
                upper = self._ask_numeric("What is the upper bound?")
                if upper >= lower:
                    break
                self.add_notice("Upper bound must be greater than or equal to the lower bound.")
            return {
                "name": name,
                "value_type": "range",
                "lower_bound": lower,
                "upper_bound": upper,
                "unit": self._ask_unit(),
            }

        return {
            "name": name,
            "value_type": "text",
            "value": self._ask_text("What is the text value?", max_length=160),
        }

    def _store_characteristic(self, target: dict, characteristic: dict) -> tuple[bool, str]:
        if target["kind"] == "node":
            return self.model.add_characteristic(target["node_id"], characteristic)
        return self.model.add_exchange_characteristic(
            target["source"],
            target["target"],
            target["key"],
            characteristic,
        )

    def capture_characteristics(self) -> None:
        targets = self._characteristic_targets()
        if not targets:
            return

        if not self.ask_yes_no(
            "Would you like to add measurable or descriptive characteristics?",
            "Characteristics capture values such as limits, durations, capacities, or other user-defined properties without changing the model structure.",
        ):
            return

        while True:
            choices = [(str(index), target["label"]) for index, target in enumerate(targets)]
            selected = self.ask_choice(
                "Which model item should receive a characteristic?",
                choices,
                "Choose the item whose property you want to describe.",
            )
            target = targets[int(selected)]

            while True:
                characteristic = self._build_characteristic()
                ok, error = self._store_characteristic(target, characteristic)
                if ok:
                    self.add_notice(
                        f"Added characteristic '{characteristic['name']}' to {target['label']}."
                    )
                else:
                    self.add_notice(f"Characteristic was not added: {error}")

                if not self.ask_yes_no(
                    f"Add another characteristic to {target['label']}?",
                    "Add another only when it describes a distinct property.",
                ):
                    break

            if not self.ask_yes_no(
                "Add characteristics to another model item?",
                "You can stop when the relevant model properties have been captured.",
            ):
                return
