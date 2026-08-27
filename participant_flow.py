from __future__ import annotations

from validator import normalize_whitespace, obvious_non_english_short_text


class ParticipantFlowMixin:
    """Lower-cognitive-load loop for adding additional participants/context.

    The first participant keeps the established mandatory flow. After that, the
    user enters the next participant/context element directly or types ``done``.
    Classification and graph writes still use the existing deterministic/user-
    confirmed path.
    """

    def ask_additional_participant(self) -> str | None:
        self.current_why = (
            "The model may need additional people, roles, organizations, groups, "
            "facilities, places, resources, or other real-world elements not yet captured."
        )

        while True:
            self.draw_question(
                "Who or what else is involved?",
                explanation=(
                    "Name one additional person, role, organization, group, facility, "
                    "place, resource, or context element. Type 'done' when there are no more."
                ),
                example="Fire Brigade",
                expected_structure="participant/context name or 'done'",
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available here.")
                continue

            value = normalize_whitespace(value)
            if value.casefold() == "done":
                return None
            if not value:
                self.add_notice("Enter one participant/context name or type 'done'.")
                continue
            if len(value) > 80:
                self.add_notice("Please provide one short participant name.")
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

            if not expects_activity:
                self.add_notice(
                    f"{participant_name} will be kept as operational context. "
                    "No action is required for it."
                )

            return participant_id

    def capture_participants_and_actions(self) -> None:
        # First elaborate candidates confirmed from goal wording.
        for participant_id in list(self.model.participants()):
            self.capture_actions_for_participant(participant_id)

        # The first participant remains mandatory when no candidate was found.
        if not self.model.participants():
            participant_id = self.add_manual_participant()
            self.capture_actions_for_participant(participant_id)

        # Additional participants use direct entry rather than a yes/no gate.
        while True:
            participant_id = self.ask_additional_participant()
            if participant_id is None:
                return
            self.capture_actions_for_participant(participant_id)
