from __future__ import annotations

from action_first_inline_flow import ActionFirstInlineCreationMixin
from semantic_frames import looks_structurally_complex, parse_simple_activity_frame
from validator import normalize_whitespace
from web_guided_flow import WebGuidedFlowMixin


def _capture_one_participant_minimal(self):
    """Web participant entry: validate only that a label was supplied."""
    self.current_why = (
        "This identifies one real-world person, role, organization, group, facility, "
        "place, resource, or context element involved in the operation."
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
            self.add_notice("That command is not available in this step.")
            continue

        value = normalize_whitespace(value)
        if not value:
            self.add_notice("Enter one participant or context name.")
            continue

        # Wording is user-owned. No length, language, vocabulary, solution-bias,
        # or semantic-candidate filter is applied here.
        decision = self.confirm_participant_classification(value)
        if decision is None:
            continue

        node_type, participant_name, classification = decision
        expects_activity = self.activity_expectation_for(node_type, participant_name)
        return self.add_node(
            node_type,
            participant_name,
            expects_activity=expects_activity,
            **classification,
        )


def _capture_new_context_element_minimal(self):
    """Web context entry: accept wording freely; enforce only relationship type."""
    self.current_why = (
        "A missing group, organization, facility, place, or context element can be "
        "created here without leaving the current relationship question."
    )
    while True:
        self.draw_question(
            "What is the new participant or context element?",
            explanation="Name the new participant or context element.",
            expected_structure="participant or context name",
        )
        value = normalize_whitespace(input("> ").strip())
        if self.command(value):
            continue
        if not value:
            self.add_notice("Enter one participant or context name.")
            continue

        decision = self.confirm_participant_classification(value)
        if decision is None:
            continue
        node_type, participant_name, classification = decision

        # This is a structural constraint of the relationship being created, not
        # a judgment about the words entered by the user.
        if node_type != "OperationalEntity":
            self.add_notice(
                "This relationship requires an Entity / context classification."
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


def _capture_inline_action_text_minimal(self) -> str:
    """Inline action entry: require text, but never reject its wording."""
    self.current_why = (
        "Describe the missing action first so the performer can be selected with "
        "the action already clear."
    )
    while True:
        self.draw_question(
            "What is the new action?",
            explanation="Describe the action. You will choose who performs it next.",
            expected_structure="action description",
        )
        value = input("> ").strip()

        if self.command(value):
            continue
        if value.startswith("/"):
            self.add_notice("That command is not available in this step.")
            continue

        value = normalize_whitespace(value)
        if not value:
            self.add_notice("Enter an action before choosing its performer.")
            continue
        return value


def _interpret_inline_action_text_minimal(self, performer_id: str, source_text: str) -> dict:
    """Build the minimum frame required by the graph without semantic rejection."""
    participant_name = self.model.name(performer_id)
    normalized = normalize_whitespace(source_text)

    # A clearly simple action can use the deterministic structural parser. For a
    # complex sentence, preserve the complete user text as one activity rather
    # than requiring AI, suggesting a rewrite, or blocking the workflow.
    frame_result = None
    if not looks_structurally_complex(normalized):
        try:
            frame_result = parse_simple_activity_frame(
                normalized,
                default_subject=participant_name,
            )
        except Exception:
            frame_result = None

    return self._sanitize_activity_frame(
        frame_result,
        normalized,
        participant_name,
    )


def install_minimal_web_input_policy() -> None:
    """Patch web-only entry paths that precede OAApp in the WebOAApp MRO."""
    WebGuidedFlowMixin._capture_one_participant = _capture_one_participant_minimal
    WebGuidedFlowMixin._capture_new_context_element = _capture_new_context_element_minimal
    ActionFirstInlineCreationMixin._capture_inline_action_text = _capture_inline_action_text_minimal
    ActionFirstInlineCreationMixin._interpret_inline_action_text = _interpret_inline_action_text_minimal
