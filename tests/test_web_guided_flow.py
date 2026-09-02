from __future__ import annotations

from web_guided_flow import WebGuidedFlowMixin


class FakeModel:
    def __init__(self):
        self.saved = 0

    def completeness_messages(self):
        return []

    def save(self, path):
        self.saved += 1
        return path


class FakeLifecycle(WebGuidedFlowMixin):
    def __init__(self, choices):
        self.model = FakeModel()
        self._choices = iter(choices)
        self.calls = []
        self.notice = ""

    def capture_goals(self):
        self.calls.append("goals")
        return []

    def capture_goal_candidates(self, goals):
        self.calls.append("goal_candidates")

    def capture_participants_and_actions(self):
        self.calls.append("participants")

    def capture_structure_and_environment(self):
        self.calls.append("structure")

    def capture_interactions(self):
        self.calls.append("interactions")

    def capture_communication(self):
        self.calls.append("communication")

    def capture_characteristics(self):
        self.calls.append("characteristics")

    def ask_choice(self, *args, **kwargs):
        return next(self._choices)

    def show_command_page(self, title, body):
        self.calls.append(("page", title, body))

    def add_notice(self, value):
        self.notice = value


def test_initial_pass_does_not_finish_session_until_explicit_finish():
    app = FakeLifecycle(["save", "finish"])
    app.run()
    assert app.model.saved == 2
    assert app.calls[:5] == [
        "goals",
        "goal_candidates",
        "participants",
        "structure",
        "interactions",
    ]
    assert "communication" in app.calls


def test_scope_check_does_not_require_knowledge_graph_comparison():
    app = FakeLifecycle(["finish"])
    assert app._scope_check_text() == (
        "No obvious gaps were found in the currently supported model scope."
    )


class ParticipantGateLifecycle(WebGuidedFlowMixin):
    def __init__(self):
        self.model = type("M", (), {"participants": lambda self: []})()
        self.questions = []
        self.text_prompt_used = False

    def ask_yes_no(self, question, why):
        self.questions.append(question)
        return False

    def _capture_one_participant(self):
        self.text_prompt_used = True
        raise AssertionError("free-text participant prompt should not open after No")


def test_participant_stage_uses_yes_no_gate_instead_of_typed_done():
    app = ParticipantGateLifecycle()
    app.capture_participants_and_actions()
    assert app.questions == ["Would you like to add a participant or context element?"]
    assert app.text_prompt_used is False
