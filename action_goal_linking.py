from __future__ import annotations


class ActionGoalLinkingMixin:
    """Require every action to be explicitly linked to one or more goals."""

    def _goals_for_action(self, action_id: str) -> list[str]:
        return [
            target
            for _, target, data in self.model.graph.out_edges(action_id, data=True)
            if data.get("type") == "SUPPORTS_CAPABILITY"
        ]

    def _create_goal_for_action(self, action_id: str) -> str:
        action_name = self.model.name(action_id)
        goal = self.ask_validated(
            question=f"What goal does '{action_name}' contribute to?",
            explanation="Describe the operational outcome supported by this action.",
            expected_concept="OperationalCapability",
            why="Every action must contribute to at least one explicit goal.",
        )
        return self.add_node("OperationalCapability", goal)

    def _select_goal_for_action(
        self,
        action_id: str,
        *,
        additional: bool = False,
    ) -> str:
        action_name = self.model.name(action_id)
        already_linked = set(self._goals_for_action(action_id))
        available = [
            goal_id
            for goal_id in self.model.nodes_of_type("OperationalCapability")
            if goal_id not in already_linked
        ]

        if not available:
            return self._create_goal_for_action(action_id)

        choices = [(goal_id, self.model.name(goal_id)) for goal_id in available]
        choices.append(("__new_goal__", "+ Add new goal"))
        selected = self.ask_choice(
            (
                f"Which additional goal does '{action_name}' contribute to?"
                if additional
                else f"Which goal does '{action_name}' contribute to?"
            ),
            choices,
            (
                "An action may support several goals, but it must support at least one. "
                "Select an existing goal or add a missing one."
            ),
        )
        if selected == "__new_goal__":
            return self._create_goal_for_action(action_id)
        return selected

    def _link_selected_goal(self, action_id: str, goal_id: str) -> bool:
        if self.model.has_relation(action_id, "SUPPORTS_CAPABILITY", goal_id):
            return True
        ok, error = self.model.add_relation(
            action_id,
            "SUPPORTS_CAPABILITY",
            goal_id,
        )
        if not ok:
            self.add_notice(f"Could not connect the action to the goal: {error}")
        return ok

    def link_action_to_goal(self, action_id: str) -> None:
        """Ask explicitly for one or more goals whenever a new action is created."""
        if action_id not in self.model.graph:
            return

        # Existing actions may reach this method again when duplicate semantic
        # descriptions are reused. Do not force the user to reconfirm links that
        # are already present.
        if self._goals_for_action(action_id):
            return

        while not self._goals_for_action(action_id):
            goal_id = self._select_goal_for_action(action_id)
            self._link_selected_goal(action_id, goal_id)

        action_name = self.model.name(action_id)
        while self.ask_yes_no(
            f"Does '{action_name}' contribute to another goal?",
            "One action may contribute to several operational goals.",
        ):
            goal_id = self._select_goal_for_action(action_id, additional=True)
            self._link_selected_goal(action_id, goal_id)

    def _scope_check_text(self) -> str:
        base = super()._scope_check_text()
        missing = [
            action_id
            for action_id in self.model.nodes_of_type("OperationalActivity")
            if not self._goals_for_action(action_id)
        ]
        if not missing:
            return base

        missing_lines = [
            f"- Action '{self.model.name(action_id)}' is not linked to any goal."
            for action_id in missing
        ]
        if base.startswith("No obvious gaps were found"):
            return "Things to review:\n" + "\n".join(missing_lines)
        return base + "\n" + "\n".join(missing_lines)
