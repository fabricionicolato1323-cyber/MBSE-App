from __future__ import annotations

from app_base import DEFAULT_SAVE_PATH, OAApp as BaseOAApp
from validator import normalize_whitespace, obvious_non_english_short_text


class WebGuidedFlowMixin:
    """Web-only guided lifecycle.

    The terminal application keeps its original finite run. The browser version
    stays open after the initial pass and lets the user refine or finish the
    model explicitly.
    """

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
