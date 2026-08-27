from __future__ import annotations

import copy
import re
import uuid

from app_base import RetryCharacteristic
from graph_model import validate_custom_aggregation_rule
from ontology import CONCEPT_GUIDANCE, RELATION_GUIDANCE, validate_concept_name


def _characteristic_key(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def looks_like_plural_human_label(value: str) -> bool:
    """Conservative surface-form warning for labels that denote several people."""
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]*|\d+", value.casefold())
    if not tokens:
        return False
    plural_markers = {
        "both", "many", "multiple", "numerous", "several", "various",
        "people", "persons", "personnel", "children", "men", "women",
    }
    if set(tokens) & plural_markers:
        return True
    if any(token.isdigit() and int(token) > 1 for token in tokens):
        return True
    head = tokens[-1]
    singular_s_endings = {
        "analysis", "business", "corps", "news", "operations", "process",
        "series", "species", "status",
    }
    return (
        len(head) > 3
        and head.endswith("s")
        and not head.endswith(("ss", "us", "is"))
        and head not in singular_s_endings
    )


class EnhancedOAAppMixin:
    """Focused UX improvements for characteristics and participant plurality."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._characteristic_existing_names: set[str] = set()
        self._current_characteristic_draft_name = ""

    def command(self, raw: str) -> bool:
        if raw.strip().casefold() == "/check" and self._characteristic_draft_active:
            messages = self.model.completeness_messages()
            persisted = (
                "Persisted model:\n" + "\n".join(f"- {item}" for item in messages)
                if messages
                else "Persisted model: No basic gap found."
            )
            draft_name = self._current_characteristic_draft_name or "current characteristic"
            draft = (
                f"Current draft: '{draft_name}' is incomplete and has not been written "
                "to the model yet. Finish it or use /retry to discard it."
            )
            self.show_page("MODEL CHECK", f"{persisted}\n\n{draft}")
            return True
        return super().command(raw)

    def _collect_limitation(self, concept: str) -> tuple[dict, dict]:
        parameter_name = self.ask_text(
            "What is being measured?",
            expected="short noun phrase",
            explanation="Examples include area, maximum distance, duration, capacity, or response time.",
        )
        self._current_characteristic_draft_name = parameter_name
        if _characteristic_key(parameter_name) in self._characteristic_existing_names:
            self.add_notice(
                f"'{parameter_name}' already exists for this element. "
                "Use /edit to change the existing characteristic or enter another name."
            )
            raise RetryCharacteristic

        parameter_description = self.ask_text(
            f"Describe the operational meaning of '{parameter_name}'.",
            expected="one concise sentence",
        )
        quantity_kind = self.ask_text(
            "What kind of quantity is it?",
            expected="quantity kind",
            explanation="Examples: length, area, duration, count, speed, or percentage.",
        )
        unit = self.ask_text(
            "What unit is used?",
            expected="unit symbol or unit name",
            explanation="Examples: m, km, m2, s, min, people, or percent.",
        )
        operator = self.ask_choice(
            "How is the limitation expressed?",
            [
                ("MIN", "Minimum"),
                ("MAX", "Maximum"),
                ("EQUAL", "Exact value"),
                ("RANGE", "Range with lower and upper limits"),
            ],
        )
        if operator == "RANGE":
            lower = self.ask_text(
                "What is the lower limit?",
                expected="number",
                validator=self.validate_number,
            )
            upper = self.ask_text(
                "What is the upper limit?",
                expected="number greater than or equal to the lower limit",
                validator=self._range_upper_validator(lower),
            )
            value_fields = {"lowerValue": lower, "upperValue": upper}
        else:
            value_fields = {
                "value": self.ask_text(
                    f"What is the {operator.casefold()} value?",
                    expected="number",
                    validator=self.validate_number,
                )
            }

        condition = self.ask_optional_text(
            "Under what operational condition does this limitation apply?",
            "During normal operations",
        )
        composition_allowed = CONCEPT_GUIDANCE[concept]["composition_relation"] is not None
        scope = "LOCAL"
        aggregation = ""
        custom_aggregation = ""
        if composition_allowed:
            scope = self.ask_choice(
                "If this element is decomposed, where does the limitation apply?",
                [("LOCAL", "Only to this element"), ("HIERARCHY", "Across its decomposition hierarchy")],
            )
            if scope == "HIERARCHY":
                aggregation = self.ask_choice(
                    "How should child values be combined?",
                    [(item, item) for item in ("SUM", "MIN", "MAX", "ALL", "ANY", "CUSTOM")],
                )
                if aggregation == "CUSTOM":
                    custom_aggregation = self.ask_text(
                        "Describe the custom aggregation rule.",
                        expected="one concise rule explaining how child values are combined",
                        validator=validate_custom_aggregation_rule,
                    )

        parameter_id = str(uuid.uuid4())
        parameter = {
            "id": parameter_id,
            "name": parameter_name,
            "description": parameter_description,
            "quantityKind": quantity_kind,
            "valueType": "Real",
            "unit": unit,
        }
        constraint = {
            "id": str(uuid.uuid4()),
            "name": f"{operator.title()} {parameter_name}",
            "description": f"{operator.title()} operational limitation for {parameter_name}.",
            "parameterId": parameter_id,
            "operator": operator,
            "applicableCondition": condition,
            "scope": scope,
            "aggregation": aggregation,
            "customAggregation": custom_aggregation,
            **value_fields,
        }
        warnings = self.model.characteristic_warnings([parameter], [constraint])
        if warnings:
            keep = self.ask_choice(
                "Keep this measurable characteristic despite the warnings?",
                [("yes", "Keep the supplied values"), ("retry", "Re-enter this characteristic")],
                explanation="Warnings never change the supplied values automatically.",
                context_lines=[f"  Warning: {warning}" for warning in warnings],
            )
            if keep == "retry":
                raise RetryCharacteristic
        return parameter, constraint

    def ask_limitations(
        self,
        concept: str,
        element_name: str,
        *,
        existing_names: set[str] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        parameters: list[dict] = []
        constraints: list[dict] = []
        decision = self.ask_decision(
            f"Does '{element_name}' have a measurable target, range, capacity, distance, duration, area, or limitation?",
            "These values are stored as attributes of the current model item.",
        )
        if decision != "yes":
            return parameters, constraints

        previous_names = self._characteristic_existing_names
        self._characteristic_existing_names = {
            _characteristic_key(item) for item in (existing_names or set())
        }
        try:
            add_more = True
            while add_more:
                self._characteristic_draft_active = True
                self._current_characteristic_draft_name = ""
                try:
                    parameter, constraint = self._collect_limitation(concept)
                except RetryCharacteristic:
                    self.add_notice(
                        "Current measurable characteristic discarded. Start it again from its name."
                    )
                    continue
                finally:
                    self._characteristic_draft_active = False
                parameters.append(parameter)
                constraints.append(constraint)
                self._characteristic_existing_names.add(
                    _characteristic_key(parameter["name"])
                )
                self._current_characteristic_draft_name = ""
                add_more = self.ask_decision(
                    f"Does '{element_name}' have another measurable limitation?"
                ) == "yes"
        finally:
            self._characteristic_existing_names = previous_names
            self._current_characteristic_draft_name = ""
        return parameters, constraints

    def _create_element_after_name(self, concept: str, name: str) -> str:
        ok, error = validate_concept_name(concept, name)
        if not ok:
            self.add_notice(f"Input error: {error}")
            return ""
        description = self.ask_text(
            f"Provide the core description of '{name}'.",
            expected="one concise sentence describing its operational meaning",
            explanation="The description is required before the element can be created.",
        )
        element_attributes: dict[str, object] = {}
        if concept == "OperationalEntity" and self._mentions_system(name, description):
            if not self.confirm_external_system_entity(name, description):
                self.add_notice(
                    "Participant creation cancelled. Clarify its external role before adding it."
                )
                return ""
            element_attributes["external_system_confirmed_by"] = "user"
        if concept == "OperationalActor":
            if self.ask_decision(
                f"Is '{name}' a human person or human role?",
                "Individual participants are usually human but may exceptionally be non-human.",
            ) == "yes":
                element_attributes["actor_nature"] = "HUMAN"
            else:
                confirmed = self.ask_decision(
                    f"Confirm '{name}' as an exceptional non-human individual participant?",
                    "A non-human individual participant must still be non-decomposable.",
                )
                if confirmed != "yes":
                    self.add_notice(
                        "Individual participant creation cancelled. Choose a collective or contextual participant if it can be decomposed."
                    )
                    return ""
                element_attributes.update({
                    "actor_nature": "NON_HUMAN",
                    "exception_confirmed_by": "user",
                    "non_decomposable": True,
                })
        parameters, constraints = self.ask_limitations(concept, name)
        ok, node_id, error = self.model.add_node(
            concept,
            name,
            description,
            parameters=parameters,
            constraints=constraints,
            confirmed_by="user",
            **element_attributes,
        )
        if not ok:
            self.add_notice(f"The element was not created: {error}")
            return ""
        self.add_notice(f"Added: {name} [{node_id[:8]}]")
        return node_id

    def create_element(self, concept: str) -> str:
        if concept != "OperationalActor":
            return super().create_element(concept)
        self.introduce_concept(concept)
        guidance = CONCEPT_GUIDANCE[concept]
        name = self.ask_text(
            f"Name the {guidance['friendly_name']}.",
            expected=guidance["expected_format"],
            validator=lambda value: validate_concept_name(concept, value),
            error_context=self.concept_context(concept),
        )
        selected_concept = concept
        if looks_like_plural_human_label(name):
            selected_concept = self.ask_choice(
                f"'{name}' appears to describe multiple people. How should it be modeled?",
                [
                    ("OperationalEntity", "Use the collective or contextual participant category"),
                    ("OperationalActor", "Keep it as one non-decomposable individual participant"),
                ],
                explanation=(
                    "Several people normally form a collective participant. The final classification remains your decision."
                ),
            )
        return self._create_element_after_name(selected_concept, name)

    def _characteristic_label(self, parameter: dict, constraint: dict) -> str:
        unit = str(parameter.get("unit", ""))
        return (
            f"{parameter.get('name', 'Unnamed')} — "
            f"{self.model._constraint_summary(constraint, unit)}"
        )

    def _select_characteristic(self, node_id: str, question: str) -> str:
        choices = []
        for parameter, constraints in self.model.characteristic_records(node_id):
            if len(constraints) != 1:
                continue
            choices.append(
                (str(parameter["id"]), self._characteristic_label(parameter, constraints[0]))
            )
        if not choices:
            return ""
        return self.ask_choice(question, choices)

    def _characteristic_preview(self, parameter: dict, constraint: dict) -> str:
        lines = [
            f"Name: {parameter.get('name', '')}",
            f"Meaning: {parameter.get('description', '')}",
            f"Quantity kind: {parameter.get('quantityKind', '')}",
            f"Unit: {parameter.get('unit', '')}",
            self.model._constraint_summary(constraint, str(parameter.get("unit", ""))),
            f"Condition: {constraint.get('applicableCondition', '') or '(none)'}",
            f"Scope: {constraint.get('scope', 'LOCAL')}",
        ]
        aggregation = str(constraint.get("aggregation", ""))
        if aggregation:
            lines.append(f"Aggregation: {aggregation}")
        return "\n".join(lines)

    def edit_characteristic(self, node_id: str) -> None:
        parameter_id = self._select_characteristic(
            node_id,
            "Which measurable attribute or limitation do you want to edit?",
        )
        if not parameter_id:
            self.add_notice("This element has no editable measurable characteristic.")
            return
        record = self.model.get_characteristic(node_id, parameter_id)
        if record is None:
            self.add_notice("The selected characteristic cannot be edited safely.")
            return
        original_parameter, original_constraint = record
        parameter = copy.deepcopy(original_parameter)
        constraint = copy.deepcopy(original_constraint)
        action = self.ask_choice(
            "What do you want to change?",
            [
                ("name", "Name"),
                ("meaning", "Operational meaning"),
                ("quantity", "Quantity kind"),
                ("unit", "Unit"),
                ("value", "Value or lower/upper limits"),
                ("condition", "Operational condition"),
                ("scope", "Scope and aggregation"),
                ("cancel", "Cancel"),
            ],
        )
        if action == "cancel":
            return
        if action == "name":
            new_name = self.ask_text(
                "Enter the revised characteristic name.",
                expected="short noun phrase",
            )
            if self.model.characteristic_name_exists(
                node_id,
                new_name,
                exclude_parameter_id=parameter_id,
            ):
                self.add_notice("Another characteristic already uses that name.")
                return
            parameter["name"] = new_name
            constraint["name"] = f"{str(constraint.get('operator', '')).title()} {new_name}"
            constraint["description"] = (
                f"{str(constraint.get('operator', '')).title()} operational limitation for {new_name}."
            )
        elif action == "meaning":
            parameter["description"] = self.ask_text(
                "Enter the revised operational meaning.",
                expected="one concise sentence",
            )
        elif action == "quantity":
            parameter["quantityKind"] = self.ask_text(
                "Enter the revised quantity kind.",
                expected="quantity kind",
            )
        elif action == "unit":
            parameter["unit"] = self.ask_text(
                "Enter the revised unit.",
                expected="unit symbol or unit name",
            )
        elif action == "value":
            operator = self.ask_choice(
                "How is the limitation expressed?",
                [
                    ("MIN", "Minimum"),
                    ("MAX", "Maximum"),
                    ("EQUAL", "Exact value"),
                    ("RANGE", "Range with lower and upper limits"),
                ],
            )
            for field in ("value", "lowerValue", "upperValue"):
                constraint.pop(field, None)
            constraint["operator"] = operator
            constraint["name"] = f"{operator.title()} {parameter['name']}"
            constraint["description"] = (
                f"{operator.title()} operational limitation for {parameter['name']}."
            )
            if operator == "RANGE":
                lower = self.ask_text(
                    "What is the lower limit?",
                    expected="number",
                    validator=self.validate_number,
                )
                upper = self.ask_text(
                    "What is the upper limit?",
                    expected="number greater than or equal to the lower limit",
                    validator=self._range_upper_validator(lower),
                )
                constraint["lowerValue"] = lower
                constraint["upperValue"] = upper
            else:
                constraint["value"] = self.ask_text(
                    f"What is the {operator.casefold()} value?",
                    expected="number",
                    validator=self.validate_number,
                )
        elif action == "condition":
            constraint["applicableCondition"] = self.ask_optional_text(
                "Under what operational condition does this limitation apply?",
                "During normal operations",
            )
        elif action == "scope":
            if CONCEPT_GUIDANCE[self.model.graph.nodes[node_id]["type"]]["composition_relation"] is None:
                constraint["scope"] = "LOCAL"
                constraint["aggregation"] = ""
                constraint["customAggregation"] = ""
                self.add_notice("This element is non-decomposable, so the scope remains LOCAL.")
            else:
                scope = self.ask_choice(
                    "Where does this limitation apply?",
                    [("LOCAL", "Only to this element"), ("HIERARCHY", "Across its decomposition hierarchy")],
                )
                constraint["scope"] = scope
                constraint["aggregation"] = ""
                constraint["customAggregation"] = ""
                if scope == "HIERARCHY":
                    aggregation = self.ask_choice(
                        "How should child values be combined?",
                        [(item, item) for item in ("SUM", "MIN", "MAX", "ALL", "ANY", "CUSTOM")],
                    )
                    constraint["aggregation"] = aggregation
                    if aggregation == "CUSTOM":
                        constraint["customAggregation"] = self.ask_text(
                            "Describe the custom aggregation rule.",
                            expected="one concise rule explaining how child values are combined",
                            validator=validate_custom_aggregation_rule,
                        )

        warnings = self.model.characteristic_warnings([parameter], [constraint])
        if warnings:
            keep = self.ask_choice(
                "Apply this edit despite the warnings?",
                [("yes", "Apply the supplied values"), ("no", "Cancel the edit")],
                explanation="Warnings never change values automatically.",
                context_lines=[f"  Warning: {warning}" for warning in warnings],
            )
            if keep != "yes":
                self.add_notice("Characteristic edit cancelled.")
                return

        confirmation = self.ask_choice(
            "Apply this characteristic change?",
            [("yes", "Yes"), ("no", "No")],
            context_lines=[
                "  Current:",
                *[f"    {line}" for line in self._characteristic_preview(original_parameter, original_constraint).splitlines()],
                "  New:",
                *[f"    {line}" for line in self._characteristic_preview(parameter, constraint).splitlines()],
            ],
        )
        if confirmation != "yes":
            self.add_notice("Characteristic edit cancelled.")
            return
        ok, error = self.model.replace_characteristic(
            node_id,
            parameter_id,
            parameter,
            constraint,
        )
        self.add_notice("Characteristic updated." if ok else f"Edit rejected: {error}")

    def remove_characteristic(self, node_id: str) -> None:
        parameter_id = self._select_characteristic(
            node_id,
            "Which measurable attribute or limitation do you want to remove?",
        )
        if not parameter_id:
            self.add_notice("This element has no removable measurable characteristic.")
            return
        record = self.model.get_characteristic(node_id, parameter_id)
        if record is None:
            self.add_notice("The selected characteristic cannot be removed safely.")
            return
        parameter, constraint = record
        if self.ask_decision(
            f"Remove '{parameter['name']}' from '{self.model.name(node_id)}'?",
            self._characteristic_preview(parameter, constraint),
        ) != "yes":
            self.add_notice("Characteristic removal cancelled.")
            return
        ok, error = self.model.remove_characteristic(node_id, parameter_id)
        self.add_notice("Characteristic removed." if ok else f"Removal failed: {error}")

    def edit_element(self) -> None:
        nodes = list(self.model.graph.nodes)
        if not nodes:
            self.add_notice("There is no element to edit yet.")
            return
        node_id = self.select_node("Which element do you want to edit?", nodes)
        data = self.model.graph.nodes[node_id]
        self.introduce_concept(data["type"], force=True)
        links = self.model.connected_relations(node_id)
        link_lines = []
        for source, relation, target in links:
            guidance = RELATION_GUIDANCE[relation]
            link_lines.extend([
                f"- {self.model.name(source)} -- {guidance['friendly_name']} --> {self.model.name(target)}",
                f"  Definition: {guidance['definition']}",
                f"  Example: {guidance['example']}",
            ])
        if not link_lines:
            link_lines = ["- No relationships"]
        characteristic_text = self.model.friendly_characteristics(node_id)
        if not characteristic_text:
            characteristic_text = "No measurable attributes or limitations."
        self.show_page(
            "CURRENT ELEMENT",
            f"Stable ID: {node_id}\nCategory: "
            f"{CONCEPT_GUIDANCE[data['type']]['friendly_name'].title()}\n"
            f"Name: {data['name']}\n"
            f"Description: {data['description']}\n\nMeasurable characteristics:\n"
            f"{characteristic_text}\n\nRelationships:\n" + "\n".join(link_lines),
        )
        has_characteristics = bool(data.get("parameters", []))
        choices = [
            ("core", "Name and core description"),
            ("add_limit", "Add measurable attribute or limitation"),
        ]
        if has_characteristics:
            choices.extend([
                ("edit_limit", "Edit measurable attribute or limitation"),
                ("remove_limit", "Remove measurable attribute or limitation"),
            ])
        choices.extend([
            ("metadata", "Summary, status, and review metadata"),
            ("relationships", "Relationships and endpoints"),
            ("composition", "Decompose or refine this element"),
            ("cancel", "Cancel"),
        ])
        action = self.ask_choice("What do you want to edit?", choices)
        if action == "core":
            guidance = CONCEPT_GUIDANCE[data["type"]]
            name = self.ask_text(
                "Enter the revised name.",
                expected=guidance["expected_format"],
                validator=lambda value: validate_concept_name(data["type"], value),
                error_context=self.concept_context(data["type"]),
            )
            description = self.ask_text(
                "Enter the revised core description.",
                expected="one concise sentence",
            )
            ok, error = self.model.update_node(node_id, name=name, description=description)
            self.add_notice("Element updated." if ok else f"Edit rejected: {error}")
        elif action == "add_limit":
            existing_names = {
                str(item.get("name", ""))
                for item in data.get("parameters", [])
                if isinstance(item, dict)
            }
            parameters, constraints = self.ask_limitations(
                data["type"],
                data["name"],
                existing_names=existing_names,
            )
            if parameters:
                ok, error = self.model.update_node(
                    node_id,
                    parameters=list(data.get("parameters", [])) + parameters,
                    constraints=list(data.get("constraints", [])) + constraints,
                )
                self.add_notice("Attributes added." if ok else f"Edit rejected: {error}")
        elif action == "edit_limit":
            self.edit_characteristic(node_id)
        elif action == "remove_limit":
            self.remove_characteristic(node_id)
        elif action == "metadata":
            summary = self.ask_optional_text("Enter a short summary.")
            status = self.ask_choice(
                "What is the element status?",
                [("DRAFT", "Draft"), ("REVIEWED", "Reviewed"), ("APPROVED", "Approved")],
            )
            review = self.ask_optional_text("Record a review note or decision.")
            ok, error = self.model.update_node(node_id, summary=summary, status=status, review=review)
            self.add_notice("Metadata updated." if ok else f"Edit rejected: {error}")
        elif action == "relationships":
            self.edit_relationships(node_id)
        elif action == "composition":
            if CONCEPT_GUIDANCE[data["type"]]["composition_relation"] is None:
                self.add_notice("Individual participants are leaves and cannot be decomposed.")
            else:
                self.capture_composition_for(node_id)
