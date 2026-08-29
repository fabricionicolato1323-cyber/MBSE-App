from __future__ import annotations


class FocusedRefinementMixin:
    """Make post-pass refinement start from explicit existing model selections.

    The initial guided pass keeps the established comprehensive flow. After that
    pass, refinement no longer silently iterates every participant or action.
    Instead, the user first selects the existing model element they want to work
    with (or chooses an explicit Add-new option).
    """

    _focused_participant_initial_pass_done = False
    _focused_interaction_initial_pass_done = False

    def capture_participants_and_actions(self) -> None:
        if not self._focused_participant_initial_pass_done:
            try:
                return super().capture_participants_and_actions()
            finally:
                self._focused_participant_initial_pass_done = True
        self._refine_participants_and_actions()

    def capture_interactions(self) -> None:
        if not self._focused_interaction_initial_pass_done:
            try:
                return super().capture_interactions()
            finally:
                self._focused_interaction_initial_pass_done = True
        self._refine_interactions()

    def _participant_refinement_label(self, participant_id: str) -> str:
        node_type = self.model.graph.nodes[participant_id].get("type")
        prefix = "Participant" if node_type == "OperationalActor" else "Participant / context"
        return f"{prefix}: {self.model.name(participant_id)}"

    def _refine_participants_and_actions(self) -> None:
        choices: list[tuple[str, str]] = []
        for participant_id in self.model.participants():
            choices.append(
                (f"participant:{participant_id}", self._participant_refinement_label(participant_id))
            )
        for action_id in self.model.nodes_of_type("OperationalActivity"):
            choices.append((f"action:{action_id}", f"Action: {self.model.action_label(action_id)}"))

        choices.extend(
            [
                ("__new_participant__", "+ Add new participant / context"),
                ("__new_action__", "+ Add new action"),
            ]
        )

        selected = self.ask_choice(
            "Which participant or action would you like to work on?",
            choices,
            "Choose an existing model item first so refinement stays focused and predictable.",
        )

        if selected == "__new_participant__":
            participant_id = self._capture_one_participant()
            if participant_id is not None:
                self.capture_actions_for_participant(participant_id)
            return

        if selected == "__new_action__":
            self._create_new_action_reference()
            return

        if selected.startswith("participant:"):
            participant_id = selected.split(":", 1)[1]
            self._refine_selected_participant(participant_id)
            return

        if selected.startswith("action:"):
            self._refine_selected_action(selected.split(":", 1)[1])

    def _refine_selected_participant(self, participant_id: str) -> None:
        """Refine actions and spatial/structural relations for one participant."""
        participant_name = self.model.name(participant_id)

        while True:
            choice = self.ask_choice(
                f"What would you like to refine for '{participant_name}'?",
                [
                    ("actions", "Actions performed by this participant"),
                    ("location", "Location / operational area"),
                    ("structure", "Structural membership / larger element"),
                    ("back", "Back to the next-step menu"),
                ],
                (
                    "A participant can be refined independently: add behavior, place it "
                    "in an operational area, or describe the larger element it belongs to."
                ),
            )

            if choice == "back":
                return
            if choice == "actions":
                self.capture_actions_for_participant(participant_id)
                continue
            if choice == "location":
                self._refine_participant_location(participant_id)
                continue
            if choice == "structure":
                self._refine_participant_structure(participant_id)

    def _participant_context_candidates(
        self,
        participant_id: str,
        *,
        exclude: set[str] | None = None,
    ) -> list[str]:
        excluded = set(exclude or set())
        excluded.add(participant_id)
        return [
            node_id
            for node_id in self.model.nodes_of_type("OperationalEntity")
            if node_id not in excluded
        ]

    def _refine_participant_location(self, participant_id: str) -> None:
        participant_name = self.model.name(participant_id)
        existing_locations = set(self.model.locations_for(participant_id))
        candidates = self._participant_context_candidates(
            participant_id,
            exclude=existing_locations,
        )

        location_id = self._select_existing_or_new_context(
            f"Where does {participant_name} operate?",
            candidates,
            (
                "Select an existing place or operational context, or add a missing "
                "context element. This creates a location relationship without changing "
                "the participant's organizational structure."
            ),
        )
        if not location_id:
            return

        ok, error = self.model.add_relation(
            participant_id,
            "LOCATED_IN",
            location_id,
        )
        if ok:
            self.add_notice(
                f"Added location: {participant_name} operates in {self.model.name(location_id)}"
            )
        else:
            self.add_notice(f"Could not add the location relation: {error}")

    def _refine_participant_structure(self, participant_id: str) -> None:
        participant_name = self.model.name(participant_id)
        existing_parent = self.model.structural_parent(participant_id)
        if existing_parent is not None:
            self.add_notice(
                f"{participant_name} is already part of {self.model.name(existing_parent)}."
            )
            return

        candidates = self._participant_context_candidates(participant_id)
        parent_id = self._select_existing_or_new_context(
            f"What larger element is {participant_name} part of?",
            candidates,
            (
                "Select an existing organization, group, facility, or larger context "
                "element. Use Location / operational area instead when the relationship "
                "means where the participant operates rather than what contains it structurally."
            ),
        )
        if not parent_id:
            return

        ok, error = self.model.add_relation(
            parent_id,
            "CONTAINS",
            participant_id,
        )
        if ok:
            self.add_notice(
                f"Added structure: {self.model.name(parent_id)} contains {participant_name}"
            )
        else:
            self.add_notice(f"Could not add the structural relation: {error}")

    def _refine_selected_action(self, action_id: str) -> None:
        action_label = self.model.action_label(action_id)
        choice = self.ask_choice(
            f"What would you like to refine for '{action_label}'?",
            [
                ("interactions", "Interactions from this action"),
                ("characteristics", "Characteristics / limits for this action"),
                ("related_action", "Add another action for the same participant"),
                ("back", "Back to the next-step menu"),
            ],
            "Refine one aspect of the selected action without changing unrelated model items.",
        )

        if choice == "interactions":
            self._refine_interactions_from_source(action_id)
        elif choice == "characteristics":
            self._capture_characteristics_for_action(action_id)
        elif choice == "related_action":
            self._add_action_for_same_performer(action_id)

    def _action_performers(self, action_id: str) -> list[str]:
        return [
            source
            for source, _, data in self.model.graph.in_edges(action_id, data=True)
            if data.get("type") == "PERFORMS"
        ]

    def _add_action_for_same_performer(self, action_id: str) -> None:
        performers = self._action_performers(action_id)
        if not performers:
            self.add_notice("This action has no confirmed performer to refine from.")
            return

        if len(performers) == 1:
            performer_id = performers[0]
        else:
            choices = [
                (participant_id, self._participant_refinement_label(participant_id))
                for participant_id in performers
            ]
            performer_id = self.ask_choice(
                "Which participant should receive the additional action?",
                choices,
                "Choose one of the confirmed performers of the selected action.",
            )
        self.capture_actions_for_participant(performer_id)

    def _capture_characteristics_for_action(self, action_id: str) -> None:
        target = {
            "kind": "node",
            "node_id": action_id,
            "label": f"Action: {self.model.action_label(action_id)}",
        }

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
                return

    def _capture_characteristics_for_exchange(
        self,
        source_id: str,
        target_id: str,
        edge_key,
        exchange_name: str,
    ) -> None:
        target = {
            "kind": "exchange",
            "source": source_id,
            "target": target_id,
            "key": edge_key,
            "label": (
                f"Interaction: {exchange_name} "
                f"({self.model.action_label(source_id)} -> {self.model.action_label(target_id)})"
            ),
        }

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
                return

    def _interaction_label(
        self,
        source_id: str,
        target_id: str,
        exchange_name: str,
    ) -> str:
        return (
            f"Interaction: {exchange_name} "
            f"({self.model.action_label(source_id)} -> {self.model.action_label(target_id)})"
        )

    def _capture_communication_for_refined_exchange(
        self,
        source_id: str,
        target_id: str,
        exchange_name: str,
    ) -> None:
        capture = getattr(self, "capture_communication_for_exchange", None)
        if callable(capture):
            capture(source_id, target_id, exchange_name)

    def _refine_existing_interaction(
        self,
        source_id: str,
        target_id: str,
        edge_key,
        exchange_name: str,
    ) -> None:
        while True:
            choice = self.ask_choice(
                f"What would you like to refine for '{exchange_name}'?",
                [
                    ("communication", "Communication method"),
                    ("characteristics", "Characteristics / limits"),
                    ("add_from_source", "Add another interaction from the same source action"),
                    ("back", "Back to the interaction list"),
                ],
                (
                    "An existing interaction already has a source, receiver, and exchanged item. "
                    "You can refine how it is carried, add limits, or create another interaction "
                    "from the same source action."
                ),
            )

            if choice == "back":
                return
            if choice == "communication":
                self._capture_communication_for_refined_exchange(
                    source_id,
                    target_id,
                    exchange_name,
                )
                continue
            if choice == "characteristics":
                self._capture_characteristics_for_exchange(
                    source_id,
                    target_id,
                    edge_key,
                    exchange_name,
                )
                continue
            if choice == "add_from_source":
                self._capture_interactions_for_source(source_id)
                return

    def _refine_interactions_from_source(self, source_id: str) -> None:
        source_label = self.model.action_label(source_id)
        records = [
            record
            for record in self.model.exchange_records()
            if record[0] == source_id
        ]
        choices = [
            (
                f"exchange:{index}",
                self._interaction_label(source, target, name),
            )
            for index, (source, target, _key, name) in enumerate(records)
        ]
        choices.extend(
            [
                ("__new_interaction__", "+ Add new interaction from this action"),
                ("__back__", "Back to the next-step menu"),
            ]
        )
        selected = self.ask_choice(
            f"Which interaction from '{source_label}' would you like to work on?",
            choices,
            (
                "Choose an existing interaction to refine, or explicitly add another "
                "interaction from the selected source action."
            ),
        )

        if selected == "__back__":
            return
        if selected == "__new_interaction__":
            self._capture_interactions_for_source(source_id)
            return
        if selected.startswith("exchange:"):
            try:
                record = records[int(selected.split(":", 1)[1])]
            except (IndexError, ValueError):
                self.add_notice("That interaction is no longer available.")
                return
            self._refine_existing_interaction(*record)

    def _refine_interactions(self) -> None:
        actions = self.model.nodes_of_type("OperationalActivity")
        if not actions:
            self.add_notice("No actions exist yet. Add an action before refining interactions.")
            self._create_new_action_reference()
            return

        records = self.model.exchange_records()
        choices = [
            (
                f"exchange:{index}",
                self._interaction_label(source, target, name),
            )
            for index, (source, target, _key, name) in enumerate(records)
        ]
        choices.extend(
            [
                ("__new_interaction__", "+ Add new interaction"),
                ("__back__", "Back to the loaded-model menu"),
            ]
        )
        selected = self.ask_choice(
            "Which interaction would you like to work on?",
            choices,
            (
                "Choose an existing interaction to refine its communication or limits. "
                "Choose Add new interaction when you want to define a new source-to-target exchange."
            ),
        )

        if selected == "__back__":
            return
        if selected == "__new_interaction__":
            self._capture_new_interaction()
            return
        if selected.startswith("exchange:"):
            try:
                record = records[int(selected.split(":", 1)[1])]
            except (IndexError, ValueError):
                self.add_notice("That interaction is no longer available.")
                return
            self._refine_existing_interaction(*record)

    def _capture_new_interaction(self) -> None:
        actions = self.model.nodes_of_type("OperationalActivity")
        choices = [
            (action_id, f"Action: {self.model.action_label(action_id)}")
            for action_id in actions
        ]
        choices.append(("__new_action__", "+ Add new action"))
        selected = self.ask_choice(
            "Which action should the interaction start from?",
            choices,
            (
                "Choose the source action first. The receiver action is selected immediately "
                "afterward before the exchanged item is entered."
            ),
        )

        if selected == "__new_action__":
            selected = self._create_new_action_reference()
        if selected:
            self._capture_interactions_for_source(selected)

    def _capture_interactions_for_source(self, source_id: str) -> None:
        """Create one or more interactions with source -> target -> item ordering."""
        source_label = self.model.action_label(source_id)

        while True:
            targets = [
                node_id
                for node_id in self.model.nodes_of_type("OperationalActivity")
                if node_id != source_id
            ]
            target_id = self._select_existing_or_new_action(
                "Which action should receive the interaction?",
                targets,
                (
                    "Select the receiver action now. After source and receiver are explicit, "
                    "the app will ask what is exchanged between them."
                ),
            )
            if not target_id:
                return

            target_label = self.model.action_label(target_id)
            item = self.ask_validated(
                question="What is exchanged?",
                explanation="Name the information, material, request, or item in a few words.",
                expected_concept="OperationalExchange",
                why="Naming what is exchanged makes the operational interaction explicit.",
                context=(
                    f"Source action: {source_label}. "
                    f"Receiver action: {target_label}. "
                    f"{self.model.short_context()}"
                ),
            )

            ok, error = self.model.add_relation(
                source_id,
                "OPERATIONAL_EXCHANGE",
                target_id,
                name=item,
            )
            if ok:
                self.add_notice(f"Added interaction: {item}")
                self._capture_communication_for_refined_exchange(
                    source_id,
                    target_id,
                    item,
                )
            else:
                self.add_notice(f"Could not add the interaction: {error}")

            if not self.ask_yes_no(
                f"Would you like to add another interaction from '{source_label}'?",
                "Add another only when it represents a distinct operational exchange from this source action.",
            ):
                return
