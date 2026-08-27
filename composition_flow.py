from __future__ import annotations


class CompositionFlowMixin:
    """Guided, user-owned composition and decomposition of model elements.

    Goals and actions use an explicit DECOMPOSES relation. Participant/context
    structure keeps using the existing CONTAINS relation so the graph has one
    authoritative representation for that fact. Nothing is inherited from a
    parent automatically.
    """

    def _decomposition_targets(self) -> list[tuple[str, str]]:
        targets: list[tuple[str, str]] = []
        for node_id in self.model.nodes_of_type("OperationalCapability"):
            targets.append((node_id, f"Goal: {self.model.name(node_id)}"))
        for node_id in self.model.nodes_of_type("OperationalEntity"):
            targets.append((node_id, f"Participant / context: {self.model.name(node_id)}"))
        for node_id in self.model.nodes_of_type("OperationalActivity"):
            targets.append((node_id, f"Action: {self.model.name(node_id)}"))
        return targets

    def _existing_or_new_child(self, node_type: str, name: str) -> str | None:
        existing = self.model.find_duplicate(node_type, name)
        if existing is None:
            return self.add_node(node_type, name)

        if self.ask_yes_no(
            f"'{self.model.name(existing)}' already exists. Use it as the smaller part?",
            "Reusing an existing item avoids duplicates while keeping the decision with you.",
        ):
            return existing

        self.add_notice("Nothing was added for that smaller part.")
        return None

    def _ask_explicit_performers(self, action_id: str) -> None:
        participants = self.model.active_participants()
        if not participants:
            self.add_notice(
                "No active participant is available, so the smaller action was not assigned."
            )
            return

        assigned = set(self.model.participants_for_activity(action_id))
        available = [item for item in participants if item not in assigned]

        if assigned:
            names = ", ".join(self.model.name(item) for item in assigned)
            self.add_notice(f"Existing performer assignment kept: {names}")
            if not available:
                return
            if not self.ask_yes_no(
                "Add another performer to this smaller action?",
                "Existing assignments are preserved; add another only when responsibility is shared.",
            ):
                return

        while available:
            performer = self.ask_number(
                "Who performs this smaller action?",
                available,
                self.model.name,
                "A smaller action does not automatically inherit the performer of its parent action.",
            )
            ok, error = self.model.add_relation(performer, "PERFORMS", action_id)
            if not ok:
                self.add_notice(f"Could not assign the performer: {error}")
            available = [item for item in available if item != performer]
            if not available:
                break
            if not self.ask_yes_no(
                "Does anyone else perform this smaller action?",
                "Add another performer only when responsibility is genuinely shared.",
            ):
                break

    def _ask_explicit_goal(self, action_id: str) -> None:
        goals = self.model.nodes_of_type("OperationalCapability")
        if not goals:
            return

        linked = [
            goal_id
            for goal_id in goals
            if self.model.has_relation(action_id, "SUPPORTS_CAPABILITY", goal_id)
        ]
        available = [goal_id for goal_id in goals if goal_id not in linked]

        if linked:
            names = ", ".join(self.model.name(item) for item in linked)
            self.add_notice(f"Existing goal connection kept: {names}")
            if not available:
                return
            question = "Add another goal connection for this smaller action?"
        else:
            question = "Does this smaller action directly help achieve one of the goals?"

        if not self.ask_yes_no(
            question,
            "A smaller action does not automatically inherit the goal connection of its parent action.",
        ):
            return

        goal_id = self.ask_number(
            "Which goal does this smaller action help achieve?",
            available,
            self.model.name,
            "Choose the goal explicitly; no parent relationship is copied automatically.",
        )
        ok, error = self.model.add_relation(
            action_id,
            "SUPPORTS_CAPABILITY",
            goal_id,
        )
        if not ok:
            self.add_notice(f"Could not connect the smaller action to the goal: {error}")

    def _add_goal_child(self, parent_id: str) -> None:
        value = self.ask_validated(
            question="What is the smaller goal?",
            explanation="Describe one narrower outcome that contributes to the selected goal.",
            example="Maintain timely operational awareness",
            expected_concept="OperationalCapability",
            why="Breaking a broad goal into smaller outcomes can make responsibilities and checks clearer.",
            context=f"Parent goal: {self.model.name(parent_id)}",
        )
        child_id = self._existing_or_new_child("OperationalCapability", value)
        if not child_id:
            return

        ok, error = self.model.add_relation(parent_id, "DECOMPOSES", child_id)
        if ok:
            self.add_notice(
                f"Added smaller goal: {self.model.name(parent_id)} -> {self.model.name(child_id)}"
            )
        else:
            self.add_notice(f"Could not add the goal decomposition: {error}")

    def _add_action_child(self, parent_id: str) -> None:
        value = self.ask_validated(
            question="What is the smaller action?",
            explanation="Describe one narrower operational action, without implementation details.",
            example="Assess the situation",
            expected_concept="OperationalActivity",
            why="Breaking a broad action into smaller actions can make behavior and responsibility clearer.",
            context=f"Parent action: {self.model.name(parent_id)}",
        )
        child_id = self._existing_or_new_child("OperationalActivity", value)
        if not child_id:
            return

        ok, error = self.model.add_relation(parent_id, "DECOMPOSES", child_id)
        if not ok:
            self.add_notice(f"Could not add the action decomposition: {error}")
            return

        self.add_notice(
            f"Added smaller action: {self.model.name(parent_id)} -> {self.model.name(child_id)}"
        )
        self._ask_explicit_performers(child_id)
        self._ask_explicit_goal(child_id)

    def _available_structural_children(self, parent_id: str) -> list[str]:
        return [
            node_id
            for node_id in self.model.participants()
            if node_id != parent_id
            and self.model.structural_parent(node_id) is None
        ]

    def _create_participant_child(self, parent_id: str) -> str | None:
        node_type, participant_name, classification = self.ask_participant()
        existing = self.model.find_participant_duplicate(participant_name)

        if existing is not None:
            if existing == parent_id:
                self.add_notice("An item cannot contain itself.")
                return None
            if not self.ask_yes_no(
                f"'{self.model.name(existing)}' already exists. Use it as the smaller element?",
                "Reusing an existing participant/context element avoids duplicates.",
            ):
                self.add_notice("Nothing was added for that smaller element.")
                return None
            return existing

        expects_activity = self.activity_expectation_for(node_type, participant_name)
        child_id = self.add_node(
            node_type,
            participant_name,
            expects_activity=expects_activity,
            **classification,
        )
        if not child_id:
            return None

        # Composition is captured before interaction elicitation. If the new
        # contained element is active, capture its actions now so later stages
        # can include those actions in interactions and communication.
        if self.model.expects_activity(child_id):
            self.capture_actions_for_participant(child_id)
        return child_id

    def _select_or_create_participant_child(self, parent_id: str) -> str | None:
        available = self._available_structural_children(parent_id)
        choices: list[tuple[str, str]] = []
        if available:
            choices.append(("existing", "Use an existing participant or context element"))
        choices.append(("new", "Add a new participant or context element"))

        choice = self.ask_choice(
            "How would you like to add the smaller element?",
            choices,
            "You can reuse an existing model element or define a new one.",
        )
        if choice == "new":
            return self._create_participant_child(parent_id)

        child_id = self.ask_number(
            "Which existing element is contained in it?",
            available,
            self.model.name,
            "Choose the participant or context element that belongs inside the selected element.",
        )
        return child_id

    def _add_participant_child(self, parent_id: str) -> None:
        child_id = self._select_or_create_participant_child(parent_id)
        if not child_id:
            return

        ok, error = self.model.add_relation(parent_id, "CONTAINS", child_id)
        if ok:
            self.add_notice(
                f"Added smaller participant/context element: "
                f"{self.model.name(parent_id)} -> {self.model.name(child_id)}"
            )
        else:
            self.add_notice(f"Could not add the participant/context composition: {error}")

    def capture_decomposition(self) -> None:
        targets = self._decomposition_targets()
        if not targets:
            return

        if not self.ask_yes_no(
            "Would you like to break any model item into smaller parts?",
            "Use this only when a broad goal, participant/context element, or action needs clearer smaller parts.",
        ):
            return

        while True:
            targets = self._decomposition_targets()
            selected = self.ask_choice(
                "Which item should be broken into smaller parts?",
                targets,
                "Choose one existing goal, participant/context element, or action.",
            )
            parent_id = selected
            node_type = self.model.graph.nodes[parent_id].get("type")

            while True:
                if node_type == "OperationalCapability":
                    self._add_goal_child(parent_id)
                elif node_type == "OperationalEntity":
                    self._add_participant_child(parent_id)
                elif node_type == "OperationalActivity":
                    self._add_action_child(parent_id)

                if not self.ask_yes_no(
                    f"Add another smaller part to '{self.model.name(parent_id)}'?",
                    "Add another only when it is a distinct part of the selected item.",
                ):
                    break

            if not self.ask_yes_no(
                "Break down another model item?",
                "You can stop when the useful composition/decomposition has been captured.",
            ):
                return
