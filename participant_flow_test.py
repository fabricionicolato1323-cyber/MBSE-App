from unittest.mock import patch

from participant_flow import ParticipantFlowMixin


class DummyModel:
    def __init__(self) -> None:
        self._participants = ["existing"]

    def participants(self) -> list[str]:
        return list(self._participants)


class DummyApp(ParticipantFlowMixin):
    def __init__(self) -> None:
        self.model = DummyModel()
        self.current_why = ""
        self.notices: list[str] = []
        self.questions: list[str] = []
        self.created: list[str] = []
        self.captured_actions: list[str] = []
        self.classified: list[str] = []

    def draw_question(self, question: str, **kwargs) -> None:
        self.questions.append(question)

    def command(self, value: str) -> bool:
        return False

    def add_notice(self, message: str) -> None:
        self.notices.append(message)

    def confirm_participant_classification(self, value: str):
        self.classified.append(value)
        return (
            "OperationalEntity",
            value,
            {
                "nature": "team_or_collective",
                "status": "confirmed",
                "confirmed_by": "user",
            },
        )

    def activity_expectation_for(self, node_type: str, name: str) -> bool:
        return False

    def add_node(self, node_type: str, name: str, **attributes) -> str:
        node_id = f"p{len(self.model._participants)}"
        self.model._participants.append(node_id)
        self.created.append(name)
        return node_id

    def capture_actions_for_participant(self, participant_id: str) -> None:
        self.captured_actions.append(participant_id)

    def add_manual_participant(self) -> str:
        raise AssertionError("The mandatory first-participant path should not run in this test.")


def main() -> None:
    app = DummyApp()

    # 1. Additional participant is entered directly; there is no yes/no gate.
    # 2. 'done' terminates the loop without being classified or persisted.
    with patch("builtins.input", side_effect=["Fire Brigade", "done"]):
        app.capture_participants_and_actions()

    assert app.created == ["Fire Brigade"]
    assert app.classified == ["Fire Brigade"]
    assert app.model.participants() == ["existing", "p1"]
    assert app.captured_actions == ["existing", "p1"]
    assert app.questions == [
        "Who or what else is involved?",
        "Who or what else is involved?",
    ]

    # 3. Context-only entities still keep the established no-action notice.
    assert any("operational context" in notice for notice in app.notices)

    print("Participant flow test passed (3 UX checks).")


if __name__ == "__main__":
    main()
