from __future__ import annotations

from app_base import DEFAULT_SAVE_PATH, OAApp as BaseOAApp
from validator import normalize_whitespace, obvious_non_english_short_text


class WebGuidedFlowMixin:
    """Web-only guided lifecycle and low-cognitive-load reference creation."""

    def _scope_check_text(self) -> str:
        notes = self.model.completeness_messages()
        if not notes:
            return "No obvious gaps were found in the currently supported model scope."
        return "Things to review:\n" + "\n".join(f"- {note}" for note in notes)

    def command(self, value: str) -> bool:
        raw = value.strip()
        command = raw.casefold()

        if command == "/check":
            self.show_command_page("MODEL CHECK", self._scope_check_text())
            return True

        if command == "/save":
            self.model.save(str(DEFAULT_SAVE_PATH))
            self.add_notice("Model saved.")
            return True

        if command == "/compare":
            self.show_command_page(
                "MODEL CHECK",
                "Detailed knowledge-graph diagnostics are not part of the current "
                "guided scope. Use Check for the supported model checks.",
            )
            return True

        if command in {"/done", "/quit"}:
            self.add_notice(
                "The web session remains open. Use 'Finish modeling' from the "
                "next-step menu when you want to end the session."
            )
            return True

        return super().command(value)

    def _capture_one_participant(self) -> str | None:
        self.current_why = (
            "This identifies one real-world person, role, organization, group, "
            "facility, place, resource, or context element involved in the operation."
        )
        while True:
            self.draw_question(
                "Who or what is involved?",
                explanation="Name one participant or context element.",
                expected_structure="participant or context name",
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available here.")
                continue

            value = normalize_whitespace(value)
            if not value:
                self.add_notice("Enter one participant or context name.")
                continue
            if len(value) > 80:
                self.add_notice("Please provide one short name.")
                continue
            if obvious_non_english_short_text(value):
                self.add_notice("Please answer in English only.")
                continue

            decision = self.confirm_participant_classification(value)
            if decision is None:
                self.add_notice("Candidate rejected. Nothing was added to the model.")
                continue

            node_type, participant_name, classification = decision
            expects_activity = self.activity_expectation_for(
                node_type,
                participant_name,
            )
            participant_id = self.add_node(
                node_type,
                participant_name,
                expects_activity=expects_activity,
                **classification,
            )
            return participant_id

    def _capture_new_context_element(self) -> str | None:
        """Create a structural/location reference and return to the interrupted flow."""
        self.current_why = (
            "A missing group, organization, facility, place, or context element can "
            "be created here without leaving the current relationship question."
        )
        while True:
            self.draw_question(
                "What is the new participant or context element?",
                explanation="Name the new group, organization, facility, place, or context element.",
            )
            value = normalize_whitespace(input("> ").strip())
            if self.command(value):
                continue
            if not value:
                self.add_notice("Enter one short name.")
                continue
            if obvious_non_english_short_text(value):
                self.add_notice("Please answer in English only.")
                continue

            decision = self.confirm_participant_classification(value)
            if decision is None:
                self.add_notice("Candidate rejected. Nothing was added to the model.")
                continue
            node_type, participant_name, classification = decision
            if node_type != "OperationalEntity":
                self.add_notice(
                    "This relationship needs a group, organization, facility, place, "
                    "or other context element rather than a person / role."
                )
                continue

            expects_activity = self.activity_expectation_for(node_type, participant_name)
            participant_id = self.add_node(
                node_type,
                participant_name,
                expects_activity=expects_activity,
                **classification,
            )
            if participant_id and self.model.expects_activity(participant_id):
                self.capture_actions_for_participant(participant_id)
            return participant_id

    def _select_existing_or_new_context(
        self,
        question: str,
        candidates: list[str],
        why: str,
    ) -> str | None:
        choices = [(node_id, self.model.name(node_id)) for node_id in candidates]
        choices.append(("__new_context__", "+ Add new participant / context"))
        selected = self.ask_choice(question, choices, why)
        if selected == "__new_context__":
            return self._capture_new_context_element()
        return selected

    def _select_action_performer(self) -> str | None:
        while True:
            participants = self.model.active_participants()
            choices = [(node_id, self.model.name(node_id)) for node_id in participants]
            choices.append(("__new_participant__", "+ Add new participant / context"))
            selected = self.ask_choice(
                "Who performs the new action?",
                choices,
                "Every action needs an explicit real-world performer.",
            )
            if selected != "__new_participant__":
                return selected

            participant_id = self._capture_one_participant()
            if participant_id is None:
                continue
            if not self.model.expects_activity(participant_id):
                self.add_notice(
                    "That item was kept as context and cannot perform an action. "
                    "Choose or add an active participant."
                )
                continue
            return participant_id

    def _create_new_action_reference(self) -> str | None:
        performer_id = self._select_action_performer()
        if performer_id is None:
            return None

        source_text, frame_result = self.ask_activity_frames(performer_id)
        created: list[str] = []
        for clause in frame_result.get("clauses", []):
            action_id = self.create_activity_from_frame(
                clause,
                performer_id,
                source_text,
            )
            if action_id and action_id not in created:
                created.append(action_id)

        if not created:
            self.add_notice("No new action was created.")
            return None
        if len(created) == 1:
            return created[0]
        return self.ask_number(
            "Which new action should be used here?",
            created,
            self.model.action_label,
            "Choose the newly created action that belongs in the interrupted relationship.",
        )

    def _select_existing_or_new_action(
        self,
        question: str,
        candidates: list[str],
        why: str,
    ) -> str | None:
        choices = [(node_id, self.model.action_label(node_id)) for node_id in candidates]
        choices.append(("__new_action__", "+ Add new action"))
        selected = self.ask_choice(question, choices, why)
        if selected == "__new_action__":
            return self._create_new_action_reference()
        return selected

    def link_action_to_goal(self, action_id: str) -> None:
        """Keep goal references selectable while allowing a missing goal to be created."""
        goals = self.model.nodes_of_type("OperationalCapability")
        if not goals:
            return
        if any(
            self.model.has_relation(action_id, "SUPPORTS_CAPABILITY", goal_id)
            for goal_id in goals
        ):
            return

        if len(goals) == 1:
            goal_id = goals[0]
        else:
            choices = [(goal_id, self.model.name(goal_id)) for goal_id in goals]
            choices.append(("__new_goal__", "+ Add new goal"))
            goal_id = self.ask_choice(
                "Which goal does this action help achieve?",
                choices,
                "Select an existing goal or add a missing one without leaving this flow.",
            )
            if goal_id == "__new_goal__":
                goal = self.ask_validated(
                    question="What is the new goal?",
                    explanation="Describe the desired operational outcome.",
                    expected_concept="OperationalCapability",
                    why="The new goal is created only because it is needed by the current action.",
                )
                goal_id = self.add_node("OperationalCapability", goal)

        ok, error = self.model.add_relation(
            action_id,
            "SUPPORTS_CAPABILITY",
            goal_id,
        )
        if not ok:
            self.add_notice(f"Could not connect the action to the goal: {error}")

    def capture_participants_and_actions(self) -> None:
        for participant_id in list(self.model.participants()):
            self.capture_actions_for_participant(participant_id)

        while True:
            has_participants = bool(self.model.participants())
            question = (
                "Would you like to add another participant or context element?"
                if has_participants
                else "Would you like to add a participant or context element?"
            )
            if not self.ask_yes_no(
                question,
                "Add another only when a distinct real-world participant or "
                "context element is relevant.",
            ):
                return

            participant_id = self._capture_one_participant()
            if participant_id is not None:
                self.capture_actions_for_participant(participant_id)

    def capture_structure_and_environment(self) -> None:
        """Capture structure/location with existing choices plus an Add-new escape path."""
        participants = list(self.model.participants())
        if not participants:
            return

        for participant_id in participants:
            participant_name = self.model.name(participant_id)

            if self.model.structural_parent(participant_id) is None:
                if self.ask_yes_no(
                    f"Is {participant_name} part of another group, organization, "
                    "facility, or larger element?",
                    "This captures organizational or structural membership.",
                ):
                    entity_candidates = [
                        node_id
                        for node_id in self.model.nodes_of_type("OperationalEntity")
                        if node_id != participant_id
                    ]
                    parent_id = self._select_existing_or_new_context(
                        f"What is {participant_name} part of?",
                        entity_candidates,
                        "Select an existing larger element or add a missing one.",
                    )
                    if parent_id:
                        ok, error = self.model.add_relation(
                            parent_id,
                            "CONTAINS",
                            participant_id,
                        )
                        if ok:
                            self.add_notice(
                                f"Added structure: {self.model.name(parent_id)} contains "
                                f"{participant_name}"
                            )
                        else:
                            self.add_notice(f"Could not add the structural relation: {error}")

            if not self.model.locations_for(participant_id):
                if self.ask_yes_no(
                    f"Does {participant_name} operate in or inside a place or area?",
                    "Location is kept separate from organizational or structural membership.",
                ):
                    entity_candidates = [
                        node_id
                        for node_id in self.model.nodes_of_type("OperationalEntity")
                        if node_id != participant_id
                    ]
                    location_id = self._select_existing_or_new_context(
                        f"Where does {participant_name} operate?",
                        entity_candidates,
                        "Select an existing place/context or add a missing one.",
                    )
                    if location_id:
                        ok, error = self.model.add_relation(
                            participant_id,
                            "LOCATED_IN",
                            location_id,
                        )
                        if ok:
                            self.add_notice(
                                f"Added location: {participant_name} operates in "
                                f"{self.model.name(location_id)}"
                            )
                        else:
                            self.add_notice(f"Could not add the location: {error}")

        self.capture_decomposition()

    def capture_interactions(self) -> None:
        """Capture exchanges while allowing a missing receiver action to be created inline."""
        actions = self.model.nodes_of_type("OperationalActivity")
        if not actions:
            return

        for source_id in list(actions):
            source_label = self.model.action_label(source_id)
            if not self.ask_yes_no(
                f"Does '{source_label}' exchange anything with another action?",
                "Interactions may carry information, material, requests, or other operational items.",
            ):
                continue

            add_more = True
            while add_more:
                item = self.ask_validated(
                    question="What is exchanged?",
                    explanation="Name the information, material, request, or item in a few words.",
                    expected_concept="OperationalExchange",
                    why="Naming what is exchanged makes the operational interaction explicit.",
                    context=(
                        f"Source action: {source_label}. "
                        f"{self.model.short_context()}"
                    ),
                )

                targets = [
                    node_id
                    for node_id in self.model.nodes_of_type("OperationalActivity")
                    if node_id != source_id
                ]
                target_id = self._select_existing_or_new_action(
                    "Which action receives it?",
                    targets,
                    "Select an existing receiver action or add a missing action.",
                )
                if target_id:
                    ok, error = self.model.add_relation(
                        source_id,
                        "OPERATIONAL_EXCHANGE",
                        target_id,
                        name=item,
                    )
                    if ok:
                        self.add_notice(f"Added interaction: {item}")
                    else:
                        self.add_notice(f"Could not add the interaction: {error}")

                add_more = self.ask_yes_no(
                    f"Is anything else exchanged from '{source_label}'?",
                    "Add another item only when it is a distinct operational interaction.",
                )

    def _refinement_menu(self) -> str:
        return self.ask_choice(
            "What would you like to do next?",
            [
                ("participants", "Add or refine participants and actions"),
                ("interactions", "Add or refine interactions"),
                ("characteristics", "Add or refine characteristics"),
                ("check", "Check model"),
                ("save", "Save"),
                ("finish", "Finish modeling"),
            ],
            "The model remains open until you explicitly choose Finish modeling.",
        )

    def run(self) -> None:
        print()
        print("The app provides advisory classifications and validation checks.")
        print("You remain responsible for confirming persistent model content.")

        goals = self.capture_goals()
        self.capture_goal_candidates(goals)
        self.capture_participants_and_actions()
        self.capture_structure_and_environment()
        self.capture_interactions()
        self.capture_communication()

        self.add_notice(
            "Initial guided pass complete. You can continue refining the model."
        )

        while True:
            choice = self._refinement_menu()

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

            if choice == "save":
                self.model.save(str(DEFAULT_SAVE_PATH))
                self.add_notice("Model saved.")
                continue

            if choice == "finish":
                self.model.save(str(DEFAULT_SAVE_PATH))
                print()
                print("Model saved.")
                print("Modeling session finished.")
                return
