from __future__ import annotations

from app_base import OAApp as BaseOAApp


class LoadedModelFlowMixin:
    """Resume a saved model and continue edits through relationship-aware flows.

    A loaded model is treated as an existing baseline rather than replaying the
    original elicitation from the beginning. Clear mandatory gaps are offered
    first. When the user creates a new goal, participant/context element, action,
    or interaction, the app immediately asks the relationship questions that are
    relevant to that new concept before returning to the loaded-model edit menu.
    """

    _loaded_relationship_followup_enabled = False

    def _mark_loaded_model_as_refinement(self) -> None:
        self._focused_participant_initial_pass_done = True
        self._focused_interaction_initial_pass_done = True
        self._loaded_relationship_followup_enabled = True

    def _first_loaded_gap(self) -> dict | None:
        goals = self.model.nodes_of_type("OperationalCapability")
        participants = self.model.participants()
        actions = self.model.nodes_of_type("OperationalActivity")

        if not goals:
            return {"kind": "goal", "message": "The loaded model has no operational goal."}
        if not participants:
            return {
                "kind": "participant",
                "message": "The loaded model has no participant or context element.",
            }

        for participant_id in self.model.active_participants():
            if not self.model.actions_for_participant(participant_id):
                return {
                    "kind": "participant_action",
                    "participant_id": participant_id,
                    "message": (
                        f"'{self.model.name(participant_id)}' is an active participant "
                        "but has no action."
                    ),
                }

        if not actions:
            return {"kind": "new_action", "message": "The loaded model has no operational action."}

        for action_id in actions:
            if not self.model.participants_for_activity(action_id):
                return {
                    "kind": "action_performer",
                    "action_id": action_id,
                    "message": f"'{self.model.name(action_id)}' has no confirmed performer.",
                }

        for action_id in actions:
            linked = any(
                data.get("type") == "SUPPORTS_CAPABILITY"
                for _, _, data in self.model.graph.out_edges(action_id, data=True)
            )
            if not linked:
                return {
                    "kind": "action_goal",
                    "action_id": action_id,
                    "message": f"'{self.model.name(action_id)}' is not connected to a goal.",
                }
        return None

    def _assign_loaded_action_performer(self, action_id: str) -> None:
        candidates = self.model.active_participants()
        choices = [
            (participant_id, self._participant_refinement_label(participant_id))
            for participant_id in candidates
        ]
        choices.append(("__new_participant__", "+ Add new participant / context"))
        selected = self.ask_choice(
            f"Who performs '{self.model.name(action_id)}'?",
            choices,
            "A loaded action needs at least one confirmed operational performer.",
        )
        if selected == "__new_participant__":
            selected = self._capture_one_participant()
        if not selected:
            return
        if not self.model.expects_activity(selected):
            self.add_notice("That item is context only and cannot perform an action.")
            return
        ok, error = self.model.add_relation(selected, "PERFORMS", action_id)
        if not ok:
            self.add_notice(f"Could not assign the performer: {error}")

    def _address_loaded_gap(self, gap: dict) -> None:
        kind = gap.get("kind")
        if kind == "goal":
            self._create_loaded_goal()
            return
        if kind == "participant":
            self._create_loaded_participant()
            return
        if kind == "participant_action":
            self.capture_actions_for_participant(gap["participant_id"])
            return
        if kind == "new_action":
            self._create_new_action_reference()
            return
        if kind == "action_performer":
            self._assign_loaded_action_performer(gap["action_id"])
            return
        if kind == "action_goal":
            self.link_action_to_goal(gap["action_id"])

    def _review_loaded_gaps(self) -> bool:
        reviewed_any = False
        while True:
            gap = self._first_loaded_gap()
            if gap is None:
                return reviewed_any
            if not self.ask_yes_no(
                f"{gap['message']} Would you like to address this now?",
                "The app uses the saved model itself to resume at the first clear mandatory gap.",
            ):
                return reviewed_any
            reviewed_any = True
            self._address_loaded_gap(gap)

    def create_activity_from_frame(
        self,
        clause: dict,
        default_participant_id: str,
        source_text: str,
    ) -> str | None:
        """Continue from a newly created action before returning to its parent flow."""
        existing = self.model.find_duplicate(
            "OperationalActivity",
            clause.get("activity_text", ""),
        )
        action_id = super().create_activity_from_frame(
            clause,
            default_participant_id,
            source_text,
        )
        if self._loaded_relationship_followup_enabled and action_id and not existing:
            self._continue_from_new_action(action_id)
        return action_id

    def _capture_communication_for_exchange(
        self,
        source_action: str,
        target_action: str,
        exchange_name: str,
    ) -> None:
        source_participants = self.model.participants_for_activity(source_action)
        target_participants = self.model.participants_for_activity(target_action)

        for source_participant in source_participants:
            for target_participant in target_participants:
                if source_participant == target_participant:
                    continue
                if self.model.has_communication_between(source_participant, target_participant):
                    continue

                source_name = self.model.name(source_participant)
                target_name = self.model.name(target_participant)
                if not self.ask_yes_no(
                    f"Do {source_name} and {target_name} use a communication method for '{exchange_name}'?",
                    "A new interaction between different participants may need an explicit operational communication method.",
                ):
                    continue

                medium = self.ask_validated(
                    question="How do they communicate?",
                    explanation=(
                        "Name the real-world communication method, not software or "
                        "implementation details."
                    ),
                    expected_concept="CommunicationMean",
                    why=(
                        "This records how the participants are able to support the "
                        "newly created operational interaction."
                    ),
                    context=(
                        f"Participants: {source_name} and {target_name}. "
                        f"Interaction: {exchange_name}."
                    ),
                )
                ok, error = self.model.add_relation(
                    source_participant,
                    "COMMUNICATION_MEAN",
                    target_participant,
                    name=medium,
                )
                if ok:
                    self.add_notice(f"Added communication method: {medium}")
                else:
                    self.add_notice(f"Could not add the communication method: {error}")

    def _continue_from_new_action(self, action_id: str) -> None:
        """Ask optional interaction/communication relationships for one new action."""
        action_name = self.model.name(action_id)

        while True:
            other_actions = [
                node_id
                for node_id in self.model.nodes_of_type("OperationalActivity")
                if node_id != action_id
            ]
            if not other_actions:
                self.add_notice(
                    f"'{action_name}' is connected to its performer and goal. "
                    "Add another action later if an interaction is needed."
                )
                return

            if not self.ask_yes_no(
                f"Would you like to connect '{action_name}' to another action through an interaction?",
                "After a new action is created, check whether it sends, receives, requests, or exchanges something with an existing action.",
            ):
                return

            direction = self.ask_choice(
                "What is the direction of the interaction?",
                [
                    ("outgoing", "This action sends or provides something to another action"),
                    ("incoming", "Another action sends or provides something to this action"),
                ],
                "The direction identifies the source and receiver of the new operational interaction.",
            )

            other_id = self.ask_choice(
                "Which other action is involved?",
                [(node_id, f"Action: {self.model.action_label(node_id)}") for node_id in other_actions],
                "Select an existing action. If another action is missing, add it from the loaded-model edit menu first.",
            )

            exchange_name = self.ask_validated(
                question="What is exchanged?",
                explanation="Name the information, material, request, or operational item in a few words.",
                expected_concept="OperationalExchange",
                why="Naming what is exchanged makes the relationship between the actions explicit.",
                context=(
                    f"New action: {self.model.action_label(action_id)}. "
                    f"Other action: {self.model.action_label(other_id)}."
                ),
            )

            if direction == "incoming":
                source_id, target_id = other_id, action_id
            else:
                source_id, target_id = action_id, other_id

            ok, error = self.model.add_relation(
                source_id,
                "OPERATIONAL_EXCHANGE",
                target_id,
                name=exchange_name,
            )
            if ok:
                self.add_notice(f"Added interaction: {exchange_name}")
                self._capture_communication_for_exchange(source_id, target_id, exchange_name)
            else:
                self.add_notice(f"Could not add the interaction: {error}")

            if not self.ask_yes_no(
                f"Would you like to add another interaction involving '{action_name}'?",
                "Add another only when it represents a distinct operational exchange involving the new action.",
            ):
                return

    def _continue_from_new_goal(self, goal_id: str) -> None:
        goal_name = self.model.name(goal_id)
        while True:
            candidates = [
                action_id
                for action_id in self.model.nodes_of_type("OperationalActivity")
                if not self.model.has_relation(action_id, "SUPPORTS_CAPABILITY", goal_id)
            ]
            if not candidates:
                return
            if not self.ask_yes_no(
                f"Does an existing action contribute to '{goal_name}'?",
                "A new goal can be connected immediately to actions that already support that operational outcome.",
            ):
                return
            action_id = self.ask_choice(
                "Which action contributes to this goal?",
                [(node_id, f"Action: {self.model.action_label(node_id)}") for node_id in candidates],
                "Select one existing action that directly supports the new goal.",
            )
            ok, error = self.model.add_relation(action_id, "SUPPORTS_CAPABILITY", goal_id)
            if not ok:
                self.add_notice(f"Could not connect the action to the goal: {error}")

    def _loaded_context_candidates(self, participant_id: str) -> list[str]:
        return [
            node_id
            for node_id in self.model.nodes_of_type("OperationalEntity")
            if node_id != participant_id
        ]

    def _select_loaded_context_relation(
        self,
        question: str,
        participant_id: str,
    ) -> str | None:
        candidates = self._loaded_context_candidates(participant_id)
        if not candidates:
            return None
        return self.ask_choice(
            question,
            [(node_id, f"Participant / context: {self.model.name(node_id)}") for node_id in candidates],
            "Select an existing participant/context element. A missing element can be added from the loaded-model edit menu.",
        )

    def _continue_from_new_participant(self, participant_id: str) -> None:
        participant_name = self.model.name(participant_id)

        if self.model.expects_activity(participant_id):
            self.capture_actions_for_participant(participant_id)

        context_candidates = self._loaded_context_candidates(participant_id)
        if context_candidates and self.model.structural_parent(participant_id) is None:
            if self.ask_yes_no(
                f"Is {participant_name} part of another group, organization, facility, or larger element?",
                "A new participant/context element may have an organizational or structural parent.",
            ):
                parent_id = self._select_loaded_context_relation(
                    f"What is {participant_name} part of?",
                    participant_id,
                )
                if parent_id:
                    ok, error = self.model.add_relation(parent_id, "CONTAINS", participant_id)
                    if not ok:
                        self.add_notice(f"Could not add the structural relation: {error}")

        context_candidates = self._loaded_context_candidates(participant_id)
        if context_candidates and not self.model.locations_for(participant_id):
            if self.ask_yes_no(
                f"Does {participant_name} operate in or inside a place or area?",
                "Location is a separate relationship from organizational structure.",
            ):
                location_id = self._select_loaded_context_relation(
                    f"Where does {participant_name} operate?",
                    participant_id,
                )
                if location_id:
                    ok, error = self.model.add_relation(participant_id, "LOCATED_IN", location_id)
                    if not ok:
                        self.add_notice(f"Could not add the location relation: {error}")

    def _create_loaded_goal(self) -> str:
        goal = self.ask_validated(
            question="What is the new goal?",
            explanation="Describe the desired operational outcome, not a system or implementation.",
            expected_concept="OperationalCapability",
            why="A newly added goal gives the model another explicit operational outcome.",
        )
        goal_id = self.add_node("OperationalCapability", goal)
        self._continue_from_new_goal(goal_id)
        return goal_id

    def _create_loaded_participant(self) -> str | None:
        participant_id = self._capture_one_participant()
        if participant_id is not None:
            self._continue_from_new_participant(participant_id)
        return participant_id

    def _loaded_refinement_menu(self) -> str:
        return self.ask_choice(
            "What would you like to change in the loaded model?",
            [
                ("new_goal", "Add new goal"),
                ("new_participant", "Add new participant / context"),
                ("new_action", "Add new action"),
                ("participants", "Refine existing participants and actions"),
                ("interactions", "Refine existing interactions"),
                ("characteristics", "Refine characteristics / limits"),
                ("check", "Check model"),
                ("finish", "Finish modeling"),
            ],
            "A new concept is followed immediately by the relevant relationship questions before this menu appears again.",
        )

    def _run_loaded_refinement_loop(self) -> None:
        while True:
            choice = self._loaded_refinement_menu()

            if choice == "new_goal":
                self._create_loaded_goal()
                continue
            if choice == "new_participant":
                self._create_loaded_participant()
                continue
            if choice == "new_action":
                self._create_new_action_reference()
                continue
            if choice == "participants":
                self.capture_participants_and_actions()
                continue
            if choice == "interactions":
                self.capture_interactions()
                BaseOAApp.capture_communication(self)
                continue
            if choice == "characteristics":
                self.capture_characteristics()
                continue
            if choice == "check":
                self.show_command_page("MODEL CHECK", self._scope_check_text())
                continue
            if choice == "finish":
                print()
                print("Modeling session finished.")
                return

    def run(self) -> None:
        self._mark_loaded_model_as_refinement()
        model_name = str(self.model.graph.graph.get("model_name") or "loaded model")
        self.add_notice(f"Loaded model: {model_name}")

        reviewed_any = self._review_loaded_gaps()
        if not reviewed_any and self._first_loaded_gap() is None:
            wants_edit = self.ask_yes_no(
                "The loaded model has no obvious mandatory gaps. Would you like to edit or refine something?",
                "If you choose Yes, the app will let you add or refine concepts and will follow every new concept with its relevant relationship questions.",
            )
            if not wants_edit:
                self.add_notice(
                    "No edit selected. You can still check or finish the loaded model, and Save model remains available in the header."
                )
        self._run_loaded_refinement_loop()
