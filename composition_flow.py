from __future__ import annotations


class CompositionFlowMixin:
    """Guided, user-owned decomposition of goals and actions.

    Structural composition of participants/context continues to use the existing
    part-of flow. This mixin adds explicit goal/action decomposition without
    automatic inheritance of performers, goals, or characteristics.
    """

    def _decomposition_targets(self) -> list[tuple[str, str]]:
        targets: list[tuple[str, str]] = []
        for node_id in self.model.nodes_of_type("OperationalCapability"):
            targets.append((node_id, f"Goal: {self.model.name(node_id)}"))
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

        available = list(participants)
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

        if not self.ask_yes_no(
            "Does this smaller action directly help achieve one of the goals?",
            "A smaller action does not automatically inherit the goal connection of its parent action.",
        ):
            return

        goal_id = self.ask_number(
            "Which goal does this smaller action help achieve?",
            goals,
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

        ok, error = self.model.add_relation(
            parent_id,
            "DECOMPOSES",
            child_id,
        )
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

        ok, error = self.model.add_relation(
            parent_id,
            "DECOMPOSES",
            child_id,
        )
        if not ok:
            self.add_notice(f"Could not add the action decomposition: {error}")
            return

        self.add_notice(
            f"Added smaller action: {self.model.name(parent_id)} -> {self.model.name(child_id)}"
        )
        self._ask_explicit_performers(child_id)
        self._ask_explicit_goal(child_id)

    def capture_decomposition(self) -> None:
        targets = self._decomposition_targets()
        if not targets:
            return

        if not self.ask_yes_no(
            "Would you like to break any goal or action into smaller parts?",
            "Use decomposition only when a broad item needs clearer smaller parts.",
        ):
            return

        while True:
            targets = self._decomposition_targets()
            selected = self.ask_choice(
                "Which item should be broken into smaller parts?",
                targets,
                "Choose one existing goal or action.",
            )
            parent_id = selected
            node_type = self.model.graph.nodes[parent_id].get("type")

            while True:
                if node_type == "OperationalCapability":
                    self._add_goal_child(parent_id)
                elif node_type == "OperationalActivity":
                    self._add_action_child(parent_id)

                if not self.ask_yes_no(
                    f"Add another smaller part to '{self.model.name(parent_id)}'?",
                    "Add another only when it is a distinct part of the selected item.",
                ):
                    break

            if not self.ask_yes_no(
                "Break down another goal or action?",
                "You can stop when the useful decomposition has been captured.",
            ):
                return
