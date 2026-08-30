from __future__ import annotations


class DirectLoadedModelResumeMixin:
    """Resume a loaded model from a concept-first Operational Analysis menu.

    The loaded-model conversation is intentionally limited to the concepts that
    can be edited in this viewpoint. Model completeness is reported continuously
    by the Completion panel, so loading a model no longer starts with a separate
    conversational gap review and the menu no longer exposes Check model or
    Finish modeling actions.
    """

    _LOADED_CONCEPT_LABELS = {
        "capability": "Operational Capability",
        "entity": "Operational Entity",
        "actor": "Operational Actor",
        "activity": "Operational Activity",
        "exchange": "Operational Exchange",
        "communication": "Communication Mean",
    }

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

    def _loaded_refinement_menu(self) -> str:
        """Show only concepts that belong to the current OA viewpoint."""
        return self.ask_choice(
            "What would you like to change in the loaded model?",
            [
                ("capability", "Operational Capability"),
                ("entity", "Operational Entity"),
                ("actor", "Operational Actor"),
                ("activity", "Operational Activity"),
                ("exchange", "Operational Exchange"),
                ("communication", "Communication Mean"),
            ],
            (
                "Choose one Operational Analysis concept. The Completion panel "
                "continuously reports missing or incomplete model structure."
            ),
        )

    def _loaded_change_mode(self, concept: str) -> str:
        label = self._LOADED_CONCEPT_LABELS[concept]
        return self.ask_choice(
            f"What would you like to do with {label}?",
            [
                ("modify", "Modify existing"),
                ("add", "Add new"),
            ],
            (
                "Modify existing continues with an element already in the model. "
                "Add new enters the normal creation flow for this concept."
            ),
        )

    def _create_loaded_participant_of_type(self, node_type: str) -> str:
        label = self._LOADED_CONCEPT_LABELS[
            "actor" if node_type == "OperationalActor" else "entity"
        ]
        name = self.ask_validated(
            question=f"What is the new {label}?",
            explanation="Enter one short operational name.",
            expected_concept=node_type,
            why=f"This adds one explicit {label} to the loaded model.",
        )

        if node_type == "OperationalActor":
            nature = "human_individual"
        else:
            nature = self.ask_entity_nature("unspecified")

        participant_id = self.add_node(
            node_type,
            name,
            expects_activity=self.activity_expectation_for(node_type, name),
            nature=nature,
            classification_source="user_selected_concept",
            classification_evidence="user_confirmed",
            classification_reason=(
                f"The user explicitly selected {label} before creating this model element."
            ),
        )
        self._continue_from_new_participant(participant_id)
        return participant_id

    def _select_existing_node(self, node_type: str, label: str) -> str | None:
        node_ids = self.model.nodes_of_type(node_type)
        if not node_ids:
            self.add_notice(f"No {label} exists yet. Choose Add new to create one.")
            return None
        return self.ask_choice(
            f"Which {label} would you like to modify?",
            [(node_id, self.model.name(node_id)) for node_id in node_ids],
            f"Choose one existing {label} so the refinement remains focused.",
        )

    def _modify_loaded_capability(self) -> None:
        goal_id = self._select_existing_node(
            "OperationalCapability",
            "Operational Capability",
        )
        if not goal_id:
            return
        self._continue_from_new_goal(goal_id)

    def _modify_loaded_participant(self, node_type: str) -> None:
        label = "Operational Actor" if node_type == "OperationalActor" else "Operational Entity"
        participant_id = self._select_existing_node(node_type, label)
        if not participant_id:
            return
        self._refine_selected_participant(participant_id)

    def _modify_loaded_activity(self) -> None:
        action_id = self._select_existing_node(
            "OperationalActivity",
            "Operational Activity",
        )
        if not action_id:
            return
        self._refine_selected_action(action_id)

    def _select_loaded_exchange(self) -> tuple[str, str, object, str] | None:
        records = list(self.model.exchange_records())
        if not records:
            self.add_notice(
                "No Operational Exchange exists yet. Choose Add new to create one."
            )
            return None

        selected = self.ask_choice(
            "Which Operational Exchange would you like to work on?",
            [
                (
                    f"exchange:{index}",
                    self._interaction_label(source, target, name),
                )
                for index, (source, target, _key, name) in enumerate(records)
            ],
            "Choose one existing exchange so the next questions stay focused.",
        )
        try:
            return records[int(selected.split(":", 1)[1])]
        except (IndexError, ValueError, AttributeError):
            self.add_notice("That Operational Exchange is no longer available.")
            return None

    def _modify_loaded_exchange(self) -> None:
        record = self._select_loaded_exchange()
        if not record:
            return
        self._refine_existing_interaction(*record)

    def _work_on_loaded_communication(self) -> None:
        """Communication Means are always refined in the context of an exchange."""
        record = self._select_loaded_exchange()
        if not record:
            return
        source, target, _key, name = record
        self.capture_communication_for_exchange(source, target, name)

    def _run_loaded_concept_action(self, concept: str, mode: str) -> None:
        if concept == "capability":
            if mode == "add":
                self._create_loaded_goal()
            else:
                self._modify_loaded_capability()
            return

        if concept == "entity":
            if mode == "add":
                self._create_loaded_participant_of_type("OperationalEntity")
            else:
                self._modify_loaded_participant("OperationalEntity")
            return

        if concept == "actor":
            if mode == "add":
                self._create_loaded_participant_of_type("OperationalActor")
            else:
                self._modify_loaded_participant("OperationalActor")
            return

        if concept == "activity":
            if mode == "add":
                self._create_new_action_reference()
            else:
                self._modify_loaded_activity()
            return

        if concept == "exchange":
            if mode == "add":
                self._capture_new_interaction()
            else:
                self._modify_loaded_exchange()
            return

        if concept == "communication":
            # The existing per-exchange communication flow already lets the user
            # select an existing medium or add a new one. Reuse that authoritative
            # flow for both entry paths instead of creating parallel logic.
            self._work_on_loaded_communication()

    def _run_loaded_refinement_loop(self) -> None:
        """Return to the concept menu after one focused change at a time."""
        while True:
            concept = self._loaded_refinement_menu()
            mode = self._loaded_change_mode(concept)
            self._run_loaded_concept_action(concept, mode)

    def run(self) -> None:
        self._mark_loaded_model_as_refinement()
        model_name = str(self.model.graph.graph.get("model_name") or "loaded model")
        self.add_notice(f"Loaded model: {model_name}")

        # Completion is the continuous validator. Do not interrupt a loaded
        # session with a second conversational model-check workflow.
        self._run_loaded_refinement_loop()
