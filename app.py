"""Deterministic terminal flow for building a persistent Arcadia OA model."""

from __future__ import annotations

import os
import re
import sys
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from graph_model import (
    MigrationConfirmationRequired,
    ModelLoadError,
    OAGraph,
    validate_custom_aggregation_rule,
)
from ontology import (
    CONCEPT_GUIDANCE,
    NODE_TYPES,
    PARTICIPANT_TYPES,
    RELATION_GUIDANCE,
    validate_concept_name,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SAVE_PATH = BASE_DIR / "oa_model.json"
COMMAND_BAR = (
    "/show  /check  /save  /load  /edit  /delete  /undo  /back  /retry  /clc  /done  /quit"
)


class RetryCharacteristic(Exception):
    """Restart the current unpersisted measurable-characteristic draft."""


class OAApp:
    def __init__(self) -> None:
        self.model = OAGraph()
        self.notice = ""
        self._introduced_concepts: set[str] = set()
        self._introduced_relations: set[str] = set()
        self._characteristic_draft_active = False

    # ------------------------------------------------------------------
    # Terminal presentation and commands
    # ------------------------------------------------------------------
    def add_notice(self, message: str) -> None:
        if message:
            self.notice = f"{self.notice}\n{message}".strip()

    def draw_question(
        self,
        question: str,
        *,
        expected: str = "",
        explanation: str = "",
        lines: list[str] | None = None,
    ) -> None:
        print()
        print("=" * 72)
        print("GUIDED OPERATIONAL MODEL BUILDER")
        print("=" * 72)
        print(f"Commands: {COMMAND_BAR}")
        print("-" * 72)
        if self.notice:
            print(self.notice)
            print("-" * 72)
            self.notice = ""
        print(question)
        if expected:
            print(f"  Expected answer: {expected}")
        if explanation:
            print(f"  {explanation}")
        for line in lines or []:
            print(line)
        print()

    @staticmethod
    def show_page(title: str, body: str) -> None:
        print()
        print("=" * 72)
        print(title)
        print("=" * 72)
        print(body)
        input("\nPress Enter to continue...")

    def command(self, raw: str) -> bool:
        value = raw.strip()
        command = value.casefold()
        if not command.startswith("/"):
            return False
        if command == "/show":
            self.show_page("MODEL SO FAR", self.model.friendly_show())
        elif command == "/check":
            messages = self.model.completeness_messages()
            body = "\n".join(f"- {item}" for item in messages) or "No basic gap found."
            self.show_page("MODEL CHECK", body)
        elif command == "/save":
            self.add_notice(f"Saved: {self.model.save(str(DEFAULT_SAVE_PATH))}")
        elif command == "/load":
            if not DEFAULT_SAVE_PATH.exists():
                self.add_notice(f"No saved model found at {DEFAULT_SAVE_PATH}.")
            else:
                try:
                    self.model.load(str(DEFAULT_SAVE_PATH))
                except MigrationConfirmationRequired as migration:
                    summary = "\n".join(f"- {item}" for item in migration.plan.migration_summary)
                    decision = self.ask_decision(
                        "Load this legacy model after applying the migration in memory?",
                        summary,
                    )
                    if decision == "yes":
                        self.model.apply_load(migration.plan)
                        self.add_notice(f"Migrated and loaded: {DEFAULT_SAVE_PATH}")
                    else:
                        self.add_notice("Load cancelled; the active model was not changed.")
                except ModelLoadError as error:
                    self.add_notice(f"Load rejected; the active model was not changed: {error}")
                else:
                    self.add_notice(f"Loaded: {DEFAULT_SAVE_PATH}")
        elif command == "/edit":
            self.edit_element()
        elif command == "/delete":
            self.delete_element()
        elif command in {"/undo", "/back"}:
            if self.model.undo():
                message = f"Undone: {self.model.last_undo_description}."
                if self._characteristic_draft_active:
                    message += " Current attribute draft was not changed; use /retry to restart it."
                self.add_notice(message)
            else:
                self.add_notice("Nothing to undo.")
        elif command == "/retry":
            if self._characteristic_draft_active:
                raise RetryCharacteristic
            self.add_notice("There is no current measurable characteristic to retry.")
        elif command == "/clc":
            os.system("cls" if os.name == "nt" else "clear")
            self.notice = ""
        elif command == "/done":
            path = self.model.save(str(DEFAULT_SAVE_PATH))
            print(f"\nSaved: {path}\nFinished.")
            raise SystemExit(0)
        elif command == "/quit":
            print("\nExiting without an automatic save.")
            raise SystemExit(0)
        else:
            self.add_notice("Unknown command. Use one of the commands shown above.")
        return True

    # ------------------------------------------------------------------
    # One-question-at-a-time input primitives
    # ------------------------------------------------------------------
    def ask_choice(
        self,
        question: str,
        choices: list[tuple[str, str]],
        *,
        explanation: str = "Choose one number.",
        context_lines: list[str] | None = None,
    ) -> str:
        while True:
            lines = list(context_lines or [])
            lines.extend(f"  {index}. {label}" for index, (_, label) in enumerate(choices, 1))
            self.draw_question(
                question,
                expected="one number from the list",
                explanation=explanation,
                lines=lines,
            )
            value = input("> ").strip()
            if self.command(value):
                continue
            try:
                selected = int(value) - 1
                if 0 <= selected < len(choices):
                    return choices[selected][0]
            except ValueError:
                pass
            self.add_notice("Please choose one of the numbers shown.")

    def ask_decision(self, question: str, explanation: str = "") -> str:
        return self.ask_choice(
            question,
            [("yes", "Yes"), ("no", "No"), ("defer", "Not now")],
            explanation=explanation or "You may defer this decision and edit it later.",
        )

    def ask_text(
        self,
        question: str,
        *,
        expected: str,
        explanation: str = "",
        validator=None,
        error_context: list[str] | None = None,
    ) -> str:
        while True:
            self.draw_question(
                question,
                expected=expected,
                explanation=explanation,
            )
            value = re.sub(r"\s+", " ", input("> ").strip())
            if self.command(value):
                continue
            if not value:
                self.add_notice("A value is required.")
                continue
            if validator:
                ok, error = validator(value)
                if not ok:
                    details = "\n".join(error_context or [])
                    self.add_notice(f"Input error: {error}" + (f"\n{details}" if details else ""))
                    continue
            return value

    def ask_optional_text(self, question: str, example: str = "") -> str:
        while True:
            lines = ["  Enter text, or type 'not now'."]
            if example:
                lines.append(f"  Example: {example}")
            self.draw_question(question, expected="text / not now", lines=lines)
            value = re.sub(r"\s+", " ", input("> ").strip())
            if self.command(value):
                continue
            if value.casefold() in {"not now", "defer", "skip"}:
                return ""
            if value:
                return value
            self.add_notice("Enter text or 'not now'.")

    @staticmethod
    def validate_number(value: str) -> tuple[bool, str]:
        try:
            number = Decimal(value.replace(",", "."))
        except InvalidOperation:
            return False, "Enter a numeric value."
        if not number.is_finite():
            return False, "Enter a finite numeric value."
        return True, ""

    def select_node(
        self,
        question: str,
        node_ids: list[str],
        *,
        exclude: set[str] | None = None,
    ) -> str:
        exclude = exclude or set()
        candidates = [node_id for node_id in node_ids if node_id not in exclude]
        choices = [
            (node_id, f"{self.model.name(node_id)} [{self.model.graph.nodes[node_id]['type']}]")
            for node_id in candidates
        ]
        return self.ask_choice(question, choices)

    # ------------------------------------------------------------------
    # Ontology-driven creation and attributes
    # ------------------------------------------------------------------
    def concept_context(self, concept: str) -> list[str]:
        guidance = CONCEPT_GUIDANCE[concept]
        return [
            f"  Definition: {guidance['definition']}",
            f"  Example: {guidance['example']}",
        ]

    def introduce_concept(self, concept: str, force: bool = False) -> None:
        if concept in self._introduced_concepts and not force:
            return
        guidance = CONCEPT_GUIDANCE[concept]
        self.show_page(
            guidance["friendly_name"].upper(),
            f"Definition: {guidance['definition']}\n\n"
            f"Expected format: {guidance['expected_format']}\n\n"
            f"Example: {guidance['example']}",
        )
        self._introduced_concepts.add(concept)

    def introduce_relation(self, relation: str, force: bool = False) -> None:
        if relation in self._introduced_relations and not force:
            return
        guidance = RELATION_GUIDANCE[relation]
        self.show_page(
            relation,
            f"Definition: {guidance['definition']}\n\nExample: {guidance['example']}",
        )
        self._introduced_relations.add(relation)

    @staticmethod
    def _range_upper_validator(lower: str):
        def validate(upper: str) -> tuple[bool, str]:
            ok, error = OAApp.validate_number(upper)
            if not ok:
                return ok, error
            lower_number = Decimal(lower.replace(",", "."))
            upper_number = Decimal(upper.replace(",", "."))
            if upper_number < lower_number:
                return False, "The upper value cannot be lower than the lower value."
            return True, ""

        return validate

    def _collect_limitation(self, concept: str) -> tuple[dict, dict]:
        parameter_name = self.ask_text(
            "What is being measured?",
            expected="short noun phrase",
            explanation="Examples include area, maximum distance, duration, capacity, or response time.",
        )
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
            [("MIN", "Minimum"), ("MAX", "Maximum"), ("EQUAL", "Exact value"), ("RANGE", "Range")],
        )
        if operator == "RANGE":
            lower = self.ask_text(
                "What is the lower value?",
                expected="number",
                validator=self.validate_number,
            )
            upper = self.ask_text(
                "What is the upper value?",
                expected="number greater than or equal to the lower value",
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
        rationale = self.ask_optional_text(
            "What is the rationale or source for this limitation?",
            "Customer safety policy",
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
            "rationale": rationale,
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

    def ask_limitations(self, concept: str, element_name: str) -> tuple[list[dict], list[dict]]:
        parameters: list[dict] = []
        constraints: list[dict] = []
        decision = self.ask_decision(
            f"Does '{element_name}' have a measurable target, range, capacity, distance, duration, area, or limitation?",
            "These operational values are captured as attributes, not as additional OA concepts.",
        )
        if decision != "yes":
            return parameters, constraints

        add_more = True
        while add_more:
            self._characteristic_draft_active = True
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
            add_more = self.ask_decision(
                f"Does '{element_name}' have another measurable limitation?"
            ) == "yes"
        return parameters, constraints

    @staticmethod
    def _mentions_system(name: str, description: str) -> bool:
        return bool(re.search(r"\bsystems?\b", f"{name} {description}", flags=re.IGNORECASE))

    def confirm_external_system_entity(self, name: str, description: str) -> bool:
        if not self._mentions_system(name, description):
            return True
        return self.ask_choice(
            f"Confirm the operational role of '{name}'.",
            [
                ("yes", "It is an existing external participant in the operational environment"),
                ("no", "It is the system being designed, or its status is not yet clear"),
            ],
            explanation=(
                "Operational Analysis must not introduce the system of interest as an "
                "Operational Entity. This confirmation does not classify the element automatically."
            ),
        ) == "yes"

    def create_element(self, concept: str) -> str:
        self.introduce_concept(concept)
        guidance = CONCEPT_GUIDANCE[concept]
        context = self.concept_context(concept)
        name = self.ask_text(
            f"Name the {guidance['friendly_name']}.",
            expected=guidance["expected_format"],
            validator=lambda value: validate_concept_name(concept, value),
            error_context=context,
        )
        description = self.ask_text(
            f"Provide the core description of '{name}'.",
            expected="one concise sentence describing its operational meaning",
            explanation="The description is required before the element can be created.",
        )
        element_attributes: dict[str, object] = {}
        if concept == "OperationalEntity" and self._mentions_system(name, description):
            if not self.confirm_external_system_entity(name, description):
                self.add_notice(
                    "Operational Entity creation cancelled. Clarify the external participant before adding it."
                )
                return ""
            element_attributes["external_system_confirmed_by"] = "user"
        if concept == "OperationalActor":
            if self.ask_decision(
                f"Is '{name}' a human person or human role?",
                "Operational Actors are usually human but may exceptionally be non-human.",
            ) == "yes":
                element_attributes["actor_nature"] = "HUMAN"
            else:
                confirmed = self.ask_decision(
                    f"Confirm '{name}' as an exceptional non-human Operational Actor?",
                    "A non-human actor must still be one non-decomposable Operational Entity.",
                )
                if confirmed != "yes":
                    self.add_notice(
                        "Operational Actor creation cancelled. Choose Operational Entity if it can be decomposed."
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

    def add_guided_relation(self, source: str, relation: str, target: str) -> bool:
        self.introduce_relation(relation)
        ok, error = self.model.add_relation(source, relation, target)
        if ok:
            self.add_notice(
                f"Added: {self.model.name(source)} --{relation}--> {self.model.name(target)}"
            )
        else:
            self.add_notice(f"Relationship not added: {error}")
        return ok

    # ------------------------------------------------------------------
    # Initial guided interview
    # ------------------------------------------------------------------
    def capture_capabilities(self) -> None:
        self.create_element("OperationalCapability")
        while self.ask_decision("Is there another distinct operational capability?") == "yes":
            self.create_element("OperationalCapability")

    def capture_participants(self) -> None:
        first = True
        while first or self.ask_decision("Is another participant or context element involved?") == "yes":
            concept = self.ask_choice(
                "What kind of operational participant is it?",
                [
                    ("OperationalActor", "Non-decomposable entity, usually a human person or role"),
                    ("OperationalEntity", "Group, organization, place, resource, context, or external participant"),
                ],
                context_lines=[
                    "  An Operational Actor is non-decomposable and usually human.",
                    "  A non-human actor requires an explicit exceptional confirmation.",
                    "  Human collectives are Operational Entities.",
                ],
            )
            participant = self.create_element(concept)
            if participant:
                capabilities = self.model.nodes_of_type("OperationalCapability")
                if capabilities and self.ask_decision(
                    f"Is '{self.model.name(participant)}' involved in an operational capability?"
                ) == "yes":
                    capability = self.select_node("Which capability?", capabilities)
                    self.add_guided_relation(participant, "INVOLVED_IN_CAPABILITY", capability)
            first = False

    def capture_activities(self) -> None:
        participants = self.model.participants()
        if not participants:
            return
        first = True
        while first or self.ask_decision("Is there another operational activity?") == "yes":
            activity = self.create_element("OperationalActivity")
            if not activity:
                first = False
                continue
            performer = self.select_node("Who or what performs this activity?", participants)
            self.add_guided_relation(performer, "PERFORMS", activity)
            while self.ask_decision("Does another participant perform the same activity?") == "yes":
                available = [
                    item for item in participants
                    if not self.model.has_relation(item, "PERFORMS", activity)
                ]
                if not available:
                    self.add_notice("All current participants are already linked.")
                    break
                other = self.select_node("Which other participant performs it?", available)
                self.add_guided_relation(other, "PERFORMS", activity)
            capabilities = self.model.nodes_of_type("OperationalCapability")
            if capabilities:
                capability = self.select_node("Which capability does this activity support?", capabilities)
                self.add_guided_relation(activity, "SUPPORTS_CAPABILITY", capability)
            first = False

    def capture_exchanges(self) -> None:
        activities = self.model.nodes_of_type("OperationalActivity")
        if len(activities) < 2:
            return
        while self.ask_decision("Is there an operational exchange between two activities?") == "yes":
            exchange = self.create_element("OperationalExchange")
            if not exchange:
                continue
            source = self.select_node("Which activity produces this exchange?", activities)
            target = self.select_node("Which activity consumes this exchange?", activities, exclude={source})
            self.add_guided_relation(exchange, "SOURCE_ACTIVITY", source)
            self.add_guided_relation(exchange, "TARGET_ACTIVITY", target)

    def capture_communication_means(self) -> None:
        participants = self.model.participants()
        if len(participants) < 2:
            return
        while self.ask_decision("Is an operational communication mean important to model?") == "yes":
            mean = self.create_element("CommunicationMean")
            if not mean:
                continue
            source = self.select_node("Which participant is the originating endpoint?", participants)
            target = self.select_node("Which participant is the receiving endpoint?", participants, exclude={source})
            self.add_guided_relation(mean, "SOURCE_PARTICIPANT", source)
            self.add_guided_relation(mean, "TARGET_PARTICIPANT", target)
            exchanges = self.model.exchanges()
            if exchanges and self.ask_decision("Does this communication mean support an exchange?") == "yes":
                exchange = self.select_node("Which exchange does it support?", exchanges)
                self.add_guided_relation(mean, "SUPPORTS_EXCHANGE", exchange)

    def capture_structure_and_location(self) -> None:
        participants = list(self.model.participants())
        entities = self.model.nodes_of_type("OperationalEntity")
        for participant in participants:
            possible_parents = [item for item in entities if item != participant]
            if possible_parents and not self.model.composition_parent(participant):
                if self.ask_decision(
                    f"Is '{self.model.name(participant)}' structurally contained by another entity?"
                ) == "yes":
                    parent = self.select_node("Which entity contains it?", possible_parents)
                    self.add_guided_relation(parent, "CONTAINS", participant)
            possible_locations = [item for item in entities if item != participant]
            if possible_locations and not self.model.locations_for(participant):
                if self.ask_decision(
                    f"Is '{self.model.name(participant)}' located in an operational place or context?"
                ) == "yes":
                    location = self.select_node("Where is it located?", possible_locations)
                    self.add_guided_relation(participant, "LOCATED_IN", location)

    # ------------------------------------------------------------------
    # Composition, refinement, and relationship allocation
    # ------------------------------------------------------------------
    def capture_composition_for(self, parent_id: str) -> None:
        if parent_id not in self.model.graph:
            return
        parent = self.model.graph.nodes[parent_id]
        relation = CONCEPT_GUIDANCE[parent["type"]]["composition_relation"]
        if relation is None:
            return
        decision = self.ask_decision(
            f"Should '{parent['name']}' be decomposed or refined now?",
            "You may choose 'Not now' and return through /edit later.",
        )
        if decision != "yes":
            return
        self.introduce_relation(relation, force=True)
        add_more = True
        while add_more:
            if parent["type"] == "OperationalEntity":
                child_type = self.ask_choice(
                    "What kind of child should be added?",
                    [
                        ("OperationalEntity", "Operational Entity"),
                        ("OperationalActor", "Operational Actor (leaf)"),
                    ],
                )
            else:
                child_type = parent["type"]
            child_id = self.create_element(child_type)
            if child_id and self.add_guided_relation(parent_id, relation, child_id):
                self.allocate_parent_links(parent_id, child_id, relation)
            add_more = self.ask_decision(
                f"Does '{parent['name']}' have another child at this level?"
            ) == "yes"

    def allocate_parent_links(self, parent_id: str, child_id: str, composition_relation: str) -> None:
        links = [
            link for link in self.model.connected_relations(parent_id)
            if link[1] not in {composition_relation, "CONTAINS", "DECOMPOSES_INTO", "REFINES_INTO"}
        ]
        for source, relation, target in links:
            other = target if source == parent_id else source
            decision = self.ask_choice(
                f"How should the relationship '{relation}' with '{self.model.name(other)}' be allocated?",
                [
                    ("parent", "Keep only on the parent"),
                    ("child", "Move to the new child"),
                    ("both", "Keep on the parent and add to the child"),
                ],
                explanation="Relationships are never reassigned automatically.",
            )
            new_source = child_id if source == parent_id else source
            new_target = child_id if target == parent_id else target
            if decision == "child":
                with self.model.user_action():
                    self.model.remove_relation(source, relation, target)
                    ok, error = self.model.add_relation(new_source, relation, new_target)
                    if not ok:
                        self.model.add_relation(source, relation, target)
                        self.add_notice(
                            f"The relationship stayed on the parent because it is not valid for the child: {error}"
                        )
                continue
            if decision == "both":
                ok, error = self.model.add_relation(new_source, relation, new_target)
                if not ok:
                    self.add_notice(
                        f"The relationship stayed on the parent because it is not valid for the child: {error}"
                    )

    def capture_all_compositions(self) -> None:
        for node_id in list(self.model.graph.nodes):
            self.capture_composition_for(node_id)

    # ------------------------------------------------------------------
    # Editing and review
    # ------------------------------------------------------------------
    def remove_existing_relation(self, node_id: str) -> None:
        links = self.model.connected_relations(node_id)
        if not links:
            self.add_notice("This element has no relationship to remove.")
            return
        selected = self.ask_choice(
            "Which relationship should be removed?",
            [
                (
                    str(index),
                    f"{self.model.name(source)} --{relation}--> {self.model.name(target)}",
                )
                for index, (source, relation, target) in enumerate(links)
            ],
        )
        source, relation, target = links[int(selected)]
        self.introduce_relation(relation, force=True)
        if self.ask_decision(
            "Remove this relationship?",
            "Only the selected relationship will be removed; its nodes remain in the model.",
        ) != "yes":
            self.add_notice("Relationship removal cancelled.")
            return
        ok, error = self.model.remove_relation(source, relation, target)
        self.add_notice("Relationship removed." if ok else f"Removal failed: {error}")

    def replace_endpoint(self, node_id: str, relation: str, targets: list[str]) -> None:
        current = self.model.relation_targets(node_id, relation)
        new_target = self.select_node(f"Select the new {relation.casefold().replace('_', ' ')}.", targets)
        if current == [new_target]:
            self.add_notice("The selected endpoint is already assigned.")
            return
        self.introduce_relation(relation, force=True)
        old_target = current[0] if current else None
        with self.model.user_action():
            if old_target:
                self.model.remove_relation(node_id, relation, old_target)
            ok, error = self.model.add_relation(node_id, relation, new_target)
            if not ok:
                if old_target:
                    self.model.add_relation(node_id, relation, old_target)
                self.add_notice(f"Endpoint edit rejected: {error}")
            else:
                self.add_notice("Endpoint updated.")

    def edit_relationships(self, node_id: str) -> None:
        node_type = self.model.graph.nodes[node_id]["type"]
        choices: list[tuple[str, str]] = []
        if node_type in PARTICIPANT_TYPES:
            choices.extend([
                ("performer", "Add a performed activity"),
                ("capability", "Add capability involvement"),
                ("location", "Add an operational location"),
            ])
            if node_type == "OperationalEntity":
                choices.append(("contains", "Add a contained entity or actor"))
        elif node_type == "OperationalActivity":
            choices.extend([
                ("performer", "Add a performer"),
                ("capability", "Add a supported capability"),
            ])
        elif node_type == "OperationalExchange":
            choices.extend([
                ("source_activity", "Replace source activity"),
                ("target_activity", "Replace target activity"),
            ])
        elif node_type == "CommunicationMean":
            choices.extend([
                ("source_participant", "Replace source participant"),
                ("target_participant", "Replace target participant"),
                ("exchange", "Add a supported exchange"),
            ])
        choices.extend([("remove", "Remove an existing relationship"), ("cancel", "Cancel")])
        action = self.ask_choice("What relationship change do you want to make?", choices)
        if action == "cancel":
            return
        if action == "remove":
            self.remove_existing_relation(node_id)
            return

        if action == "performer" and node_type in PARTICIPANT_TYPES:
            candidates = [
                item for item in self.model.nodes_of_type("OperationalActivity")
                if not self.model.has_relation(node_id, "PERFORMS", item)
            ]
            if candidates:
                target = self.select_node("Which activity does this participant perform?", candidates)
                self.add_guided_relation(node_id, "PERFORMS", target)
            else:
                self.add_notice("No unlinked activity is available.")
        elif action == "performer":
            candidates = [
                item for item in self.model.participants()
                if not self.model.has_relation(item, "PERFORMS", node_id)
            ]
            if candidates:
                source = self.select_node("Which participant performs this activity?", candidates)
                self.add_guided_relation(source, "PERFORMS", node_id)
            else:
                self.add_notice("No unlinked participant is available.")
        elif action == "capability" and node_type in PARTICIPANT_TYPES:
            candidates = [
                item for item in self.model.nodes_of_type("OperationalCapability")
                if not self.model.has_relation(node_id, "INVOLVED_IN_CAPABILITY", item)
            ]
            if candidates:
                target = self.select_node("Which capability is this participant involved in?", candidates)
                self.add_guided_relation(node_id, "INVOLVED_IN_CAPABILITY", target)
            else:
                self.add_notice("No unlinked capability is available.")
        elif action == "capability":
            candidates = [
                item for item in self.model.nodes_of_type("OperationalCapability")
                if not self.model.has_relation(node_id, "SUPPORTS_CAPABILITY", item)
            ]
            if candidates:
                target = self.select_node("Which capability does this activity support?", candidates)
                self.add_guided_relation(node_id, "SUPPORTS_CAPABILITY", target)
            else:
                self.add_notice("No unlinked capability is available.")
        elif action == "location":
            candidates = [
                item for item in self.model.nodes_of_type("OperationalEntity")
                if item != node_id and not self.model.has_relation(node_id, "LOCATED_IN", item)
            ]
            if candidates:
                target = self.select_node("Where is this participant located?", candidates)
                self.add_guided_relation(node_id, "LOCATED_IN", target)
            else:
                self.add_notice("No compatible location is available.")
        elif action == "contains":
            candidates = [
                item for item in self.model.participants()
                if item != node_id and not self.model.composition_parent(item)
            ]
            if candidates:
                target = self.select_node("Which participant is contained?", candidates)
                self.add_guided_relation(node_id, "CONTAINS", target)
            else:
                self.add_notice("No participant without a composition parent is available.")
        elif action == "source_activity":
            self.replace_endpoint(node_id, "SOURCE_ACTIVITY", self.model.nodes_of_type("OperationalActivity"))
        elif action == "target_activity":
            self.replace_endpoint(node_id, "TARGET_ACTIVITY", self.model.nodes_of_type("OperationalActivity"))
        elif action == "source_participant":
            self.replace_endpoint(node_id, "SOURCE_PARTICIPANT", self.model.participants())
        elif action == "target_participant":
            self.replace_endpoint(node_id, "TARGET_PARTICIPANT", self.model.participants())
        elif action == "exchange":
            candidates = [
                item for item in self.model.exchanges()
                if not self.model.has_relation(node_id, "SUPPORTS_EXCHANGE", item)
            ]
            if candidates:
                target = self.select_node("Which exchange does it support?", candidates)
                self.add_guided_relation(node_id, "SUPPORTS_EXCHANGE", target)
            else:
                self.add_notice("No unlinked exchange is available.")

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
                f"- {self.model.name(source)} --{relation}--> {self.model.name(target)}",
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
            f"Stable ID: {node_id}\nType: {data['type']}\nName: {data['name']}\n"
            f"Description: {data['description']}\n\nMeasurable characteristics:\n"
            f"{characteristic_text}\n\nRelationships:\n"
            + "\n".join(link_lines),
        )
        action = self.ask_choice(
            "What do you want to edit?",
            [
                ("core", "Name and core description"),
                ("limits", "Add measurable attributes or limitations"),
                ("metadata", "Summary, status, and review metadata"),
                ("relationships", "Relationships and endpoints"),
                ("composition", "Decompose or refine this element"),
                ("cancel", "Cancel"),
            ],
        )
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
        elif action == "limits":
            parameters, constraints = self.ask_limitations(data["type"], data["name"])
            if parameters:
                ok, error = self.model.update_node(
                    node_id,
                    parameters=list(data.get("parameters", [])) + parameters,
                    constraints=list(data.get("constraints", [])) + constraints,
                )
                self.add_notice("Attributes added." if ok else f"Edit rejected: {error}")
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
                self.add_notice("Operational Actors are leaves and cannot be decomposed.")
            else:
                self.capture_composition_for(node_id)

    def delete_element(self) -> None:
        nodes = list(self.model.graph.nodes)
        if not nodes:
            self.add_notice("There is no element to delete.")
            return
        node_id = self.select_node("Which element do you want to delete?", nodes)
        links = self.model.connected_relations(node_id)
        if links:
            self.show_page(
                "AFFECTED RELATIONSHIPS",
                "\n".join(
                    f"- {self.model.name(source)} --{relation}--> {self.model.name(target)}"
                    for source, relation, target in links
                ),
            )
        if self.ask_decision(
            f"Delete '{self.model.name(node_id)}' and the {len(links)} attached relationship(s)?",
            "Deletion never cascades without this explicit confirmation.",
        ) != "yes":
            self.add_notice("Deletion cancelled.")
            return
        ok, error = self.model.remove_node(node_id, cascade_confirmed=True)
        self.add_notice("Element deleted." if ok else f"Deletion failed: {error}")

    def add_element_from_menu(self) -> None:
        concept = self.ask_choice(
            "Which OA concept do you want to add?",
            [(item, CONCEPT_GUIDANCE[item]["friendly_name"].title()) for item in sorted(NODE_TYPES)],
        )
        node_id = self.create_element(concept)
        if not node_id:
            return
        if concept in PARTICIPANT_TYPES and self.model.nodes_of_type("OperationalCapability"):
            if self.ask_decision("Is this participant involved in a capability?") == "yes":
                capability = self.select_node(
                    "Which capability?",
                    self.model.nodes_of_type("OperationalCapability"),
                )
                self.add_guided_relation(node_id, "INVOLVED_IN_CAPABILITY", capability)
        elif concept == "OperationalActivity" and self.model.participants():
            performer = self.select_node("Who or what performs it?", self.model.participants())
            self.add_guided_relation(performer, "PERFORMS", node_id)
            capabilities = self.model.nodes_of_type("OperationalCapability")
            if capabilities:
                capability = self.select_node("Which capability does it support?", capabilities)
                self.add_guided_relation(node_id, "SUPPORTS_CAPABILITY", capability)
        elif concept == "OperationalExchange" and len(self.model.nodes_of_type("OperationalActivity")) >= 2:
            activities = self.model.nodes_of_type("OperationalActivity")
            source = self.select_node("Which activity produces it?", activities)
            target = self.select_node("Which activity consumes it?", activities, exclude={source})
            self.add_guided_relation(node_id, "SOURCE_ACTIVITY", source)
            self.add_guided_relation(node_id, "TARGET_ACTIVITY", target)
        elif concept == "CommunicationMean" and len(self.model.participants()) >= 2:
            source = self.select_node("Which participant is the originating endpoint?", self.model.participants())
            target = self.select_node("Which participant is the receiving endpoint?", self.model.participants(), exclude={source})
            self.add_guided_relation(node_id, "SOURCE_PARTICIPANT", source)
            self.add_guided_relation(node_id, "TARGET_PARTICIPANT", target)

    def review_loop(self) -> None:
        while True:
            action = self.ask_choice(
                "What would you like to do next?",
                [
                    ("show", "Review the model"),
                    ("add", "Add an OA element"),
                    ("edit", "Edit or decompose an element"),
                    ("delete", "Delete an element"),
                    ("check", "Check basic completeness"),
                    ("save", "Save a checkpoint"),
                    ("finish", "Finish and save"),
                ],
            )
            if action == "show":
                self.show_page("MODEL SO FAR", self.model.friendly_show())
            elif action == "add":
                self.add_element_from_menu()
            elif action == "edit":
                self.edit_element()
            elif action == "delete":
                self.delete_element()
            elif action == "check":
                messages = self.model.completeness_messages()
                self.show_page(
                    "MODEL CHECK",
                    "\n".join(f"- {item}" for item in messages) or "No basic gap found.",
                )
            elif action == "save":
                self.add_notice(f"Saved: {self.model.save(str(DEFAULT_SAVE_PATH))}")
            elif action == "finish":
                break

    def run(self) -> None:
        print()
        print("This guided flow builds a persistent Arcadia Operational Analysis model.")
        print("The user is responsible for the meaning and quality of every confirmed element.")
        self.capture_capabilities()
        self.capture_participants()
        self.capture_activities()
        self.capture_exchanges()
        self.capture_communication_means()
        self.capture_structure_and_location()
        self.capture_all_compositions()
        self.review_loop()
        path = self.model.save(str(DEFAULT_SAVE_PATH))
        print()
        print(self.model.friendly_show())
        print(f"\nSaved: {path}\nFinished.")


def main() -> None:
    try:
        OAApp().run()
    except KeyboardInterrupt:
        print("\nInterrupted. The unfinished answer was not written.")
        sys.exit(130)
    except (OSError, ValueError) as exc:
        print(f"\nApplication error: {exc}")
        sys.exit(2)


if __name__ == "__main__":
    main()
