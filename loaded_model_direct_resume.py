from __future__ import annotations

from typing import Any

from ui_guidance import configured_choices, configured_text


class DirectLoadedModelResumeMixin:
    """Resume a loaded OA model through a low-cognitive-load refinement menu.

    User-facing wording is configuration-driven and deliberately independent of
    the formal ontology names. Stable internal IDs route each choice back into
    the existing creation/refinement flows, so this layer does not redefine how
    Operational Analysis model elements are created or related.
    """

    _LOADED_UI_SECTION = "loaded_model"
    _LOADED_INTENTS = {"modify", "add"}
    _LOADED_CATEGORIES = {
        "goal",
        "participants",
        "activity",
        "exchange",
        "communication",
        "characteristics",
    }

    def _loaded_ui_text(self, key: str) -> str:
        value = configured_text(self._LOADED_UI_SECTION, key)
        if not value:
            raise RuntimeError(f"Missing loaded-model UI guidance: {key}")
        return value

    def _loaded_ui_choices(
        self,
        key: str,
        allowed: set[str],
    ) -> list[tuple[str, str]]:
        choices = [
            (choice_id, label)
            for choice_id, label in configured_choices(self._LOADED_UI_SECTION, key)
            if choice_id in allowed
        ]
        if not choices:
            raise RuntimeError(f"Missing loaded-model UI choices: {key}")
        return choices

    def _capture_communication_for_exchange(
        self,
        source_action: str,
        target_action: str,
        exchange_name: str,
    ) -> None:
        """Compatibility hook used by the loaded new-action continuation flow."""
        self.capture_communication_for_exchange(
            source_action,
            target_action,
            exchange_name,
        )

    def _loaded_change_mode(self) -> str:
        """Ask for intent before exposing any model category."""
        return self.ask_choice(
            self._loaded_ui_text("intent_question"),
            self._loaded_ui_choices("intents", self._LOADED_INTENTS),
            self._loaded_ui_text("intent_explanation"),
        )

    def _loaded_refinement_menu(self) -> str:
        """Present configured real-world vocabulary instead of ontology class names."""
        return self.ask_choice(
            self._loaded_ui_text("category_question"),
            self._loaded_ui_choices("categories", self._LOADED_CATEGORIES),
            self._loaded_ui_text("category_explanation"),
        )

    def _select_existing_node(self, node_type: str, label: str) -> str | None:
        node_ids = self.model.nodes_of_type(node_type)
        if not node_ids:
            self.add_notice(f"No {label} exists yet. Choose Add something new to create one.")
            return None
        return self.ask_choice(
            f"Which {label} would you like to modify?",
            [(node_id, self.model.name(node_id)) for node_id in node_ids],
            f"Choose one existing {label} so the change stays focused.",
        )

    def _modify_loaded_goal(self) -> None:
        goal_id = self._select_existing_node("OperationalCapability", "goal")
        if not goal_id:
            return
        self._continue_from_new_goal(goal_id)

    def _add_loaded_participant(self) -> None:
        """Reuse the normal participant entry and classification path unchanged."""
        participant_id = self.ask_additional_participant()
        if participant_id is not None:
            self.capture_actions_for_participant(participant_id)

    def _modify_loaded_participant(self) -> None:
        participant_ids = list(self.model.participants())
        if not participant_ids:
            self.add_notice(
                "No participant or context element exists yet. Choose Add something new to create one."
            )
            return

        participant_id = self.ask_choice(
            "Which person, organization, place, system, or other participant would you like to modify?",
            [(node_id, self.model.name(node_id)) for node_id in participant_ids],
            "Choose one existing participant or context element so the change stays focused.",
        )
        self._refine_selected_participant(participant_id)

    def _modify_loaded_activity(self) -> None:
        action_id = self._select_existing_node("OperationalActivity", "activity")
        if not action_id:
            return
        self._refine_selected_action(action_id)

    def _loaded_exchange_label(
        self,
        source_id: str,
        target_id: str,
        exchange_name: str,
    ) -> str:
        return (
            f"{exchange_name} "
            f"({self.model.action_label(source_id)} -> {self.model.action_label(target_id)})"
        )

    def _select_loaded_exchange(self) -> tuple[str, str, object, str] | None:
        records = list(self.model.exchange_records())
        if not records:
            self.add_notice(
                "No exchanged information or material exists yet. Choose Add something new to create one."
            )
            return None

        selected = self.ask_choice(
            "Which exchange would you like to work on?",
            [
                (
                    f"exchange:{index}",
                    self._loaded_exchange_label(source, target, name),
                )
                for index, (source, target, _key, name) in enumerate(records)
            ],
            "Choose one existing exchange so the next questions stay focused.",
        )
        try:
            return records[int(selected.split(":", 1)[1])]
        except (IndexError, ValueError, AttributeError):
            self.add_notice("That exchange is no longer available.")
            return None

    def _modify_loaded_exchange(self) -> None:
        record = self._select_loaded_exchange()
        if not record:
            return
        self._refine_existing_interaction(*record)

    def _work_on_loaded_communication(self) -> None:
        """Communication means remain refined in the context of an exchange."""
        record = self._select_loaded_exchange()
        if not record:
            return
        source, target, _key, name = record
        self.capture_communication_for_exchange(source, target, name)

    def _select_characteristic_target(self) -> dict[str, Any] | None:
        targets = self._characteristic_targets()
        if not targets:
            self.add_notice(
                "There is no model item yet that can receive a characteristic or limit."
            )
            return None

        selected = self.ask_choice(
            "Which model item should receive the characteristic or limit?",
            [(str(index), target["label"]) for index, target in enumerate(targets)],
            "Choose the item whose measurable or descriptive property you want to define.",
        )
        try:
            return targets[int(selected)]
        except (IndexError, ValueError, TypeError):
            self.add_notice("That model item is no longer available.")
            return None

    def _add_loaded_characteristic(self) -> None:
        """Reuse the existing characteristic builder and storage validation."""
        target = self._select_characteristic_target()
        if target is None:
            return

        characteristic = self._build_characteristic()
        ok, error = self._store_characteristic(target, characteristic)
        if ok:
            self.add_notice(
                f"Added characteristic '{characteristic['name']}' to {target['label']}."
            )
        else:
            self.add_notice(f"Characteristic was not added: {error}")

    def _existing_characteristic_records(
        self,
    ) -> list[tuple[dict[str, Any], int, dict[str, Any]]]:
        records: list[tuple[dict[str, Any], int, dict[str, Any]]] = []
        for target in self._characteristic_targets():
            if target["kind"] == "node":
                values = self.model.characteristics_for_node(target["node_id"])
            else:
                values = self.model.characteristics_for_exchange(
                    target["source"],
                    target["target"],
                    target["key"],
                )
            for index, characteristic in enumerate(values):
                records.append((target, index, characteristic))
        return records

    def _characteristic_record_label(
        self,
        target: dict[str, Any],
        characteristic: dict[str, Any],
    ) -> str:
        formatter = getattr(self.model, "_format_characteristic", None)
        formatted = (
            formatter(characteristic)
            if callable(formatter)
            else str(characteristic.get("name") or "Characteristic")
        )
        return f"{target['label']} — {formatted}"

    def _replace_characteristic(
        self,
        target: dict[str, Any],
        index: int,
        characteristic: dict[str, Any],
    ) -> tuple[bool, str]:
        if target["kind"] == "node":
            replace = getattr(self.model, "replace_characteristic", None)
            if not callable(replace):
                return False, "Characteristic editing is unavailable."
            return replace(target["node_id"], index, characteristic)

        replace = getattr(self.model, "replace_exchange_characteristic", None)
        if not callable(replace):
            return False, "Characteristic editing is unavailable."
        return replace(
            target["source"],
            target["target"],
            target["key"],
            index,
            characteristic,
        )

    def _modify_loaded_characteristic(self) -> None:
        records = self._existing_characteristic_records()
        if not records:
            self.add_notice(
                "No characteristic or limit exists yet. Choose Add something new to create one."
            )
            return

        selected = self.ask_choice(
            "Which characteristic or limit would you like to change?",
            [
                (
                    f"characteristic:{index}",
                    self._characteristic_record_label(target, characteristic),
                )
                for index, (target, _position, characteristic) in enumerate(records)
            ],
            "Choose one existing value or limit. Its replacement uses the same validation as creation.",
        )
        try:
            target, position, previous = records[int(selected.split(":", 1)[1])]
        except (IndexError, ValueError, AttributeError):
            self.add_notice("That characteristic or limit is no longer available.")
            return

        replacement = self._build_characteristic()
        ok, error = self._replace_characteristic(target, position, replacement)
        if ok:
            self.add_notice(
                f"Changed '{previous.get('name', 'characteristic')}' to "
                f"'{replacement['name']}' for {target['label']}."
            )
        else:
            self.add_notice(f"Characteristic was not changed: {error}")

    def _run_loaded_concept_action(self, category: str, mode: str) -> None:
        if category == "goal":
            if mode == "add":
                self._create_loaded_goal()
            else:
                self._modify_loaded_goal()
            return

        if category == "participants":
            if mode == "add":
                self._add_loaded_participant()
            else:
                self._modify_loaded_participant()
            return

        if category == "activity":
            if mode == "add":
                self._create_new_action_reference()
            else:
                self._modify_loaded_activity()
            return

        if category == "exchange":
            if mode == "add":
                self._capture_new_interaction()
            else:
                self._modify_loaded_exchange()
            return

        if category == "communication":
            # The authoritative per-exchange flow already lets the user select an
            # existing communication mean or add a new one. Reuse it for either
            # intent rather than creating a second communication implementation.
            self._work_on_loaded_communication()
            return

        if category == "characteristics":
            if mode == "add":
                self._add_loaded_characteristic()
            else:
                self._modify_loaded_characteristic()

    def _run_loaded_refinement_loop(self) -> None:
        """Return to intent after one focused change at a time."""
        while True:
            mode = self._loaded_change_mode()
            category = self._loaded_refinement_menu()
            self._run_loaded_concept_action(category, mode)

    def run(self) -> None:
        self._mark_loaded_model_as_refinement()
        model_name = str(self.model.graph.graph.get("model_name") or "loaded model")
        self.add_notice(f"Loaded model: {model_name}")

        # Completion is the continuous validator. Do not interrupt a loaded
        # session with a second conversational model-check workflow.
        self._run_loaded_refinement_loop()
