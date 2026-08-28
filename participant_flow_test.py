from unittest.mock import patch

from participant_flow import ParticipantFlowMixin


class DummyModel:
    def __init__(self, participants: list[str] | None = None) -> None:
        self._participants = list(participants or [])

    def participants(self) -> list[str]:
        return list(self._participants)


class DummyApp(ParticipantFlowMixin):
    def __init__(self, participants: list[str] | None = None) -> None:
        self.model = DummyModel(participants)
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


def main() -> None:
    # 1. With an existing participant, the next participant is entered directly.
    app = DummyApp(["existing"])
    with patch("builtins.input", side_effect=["Additional Team", "done"]):
        app.capture_participants_and_actions()

    assert app.created == ["Additional Team"]
    assert app.classified == ["Additional Team"]
    assert app.model.participants() == ["existing", "p1"]
    assert app.captured_actions == ["existing", "p1"]
    assert app.questions == [
        "Who or what else is involved?",
        "Who or what else is involved?",
    ]

    # 2. Context-only entities still keep the established no-action notice.
    assert any("operational context" in notice for notice in app.notices)

    # 3. When no participant exists, direct entry is used instead of the old
    # mandatory first-participant path.
    first = DummyApp()
    with patch("builtins.input", side_effect=["Initial Team", "done"]):
        first.capture_participants_and_actions()

    assert first.created == ["Initial Team"]
    assert first.classified == ["Initial Team"]
    assert first.questions == [
        "Who or what is involved?",
        "Who or what else is involved?",
    ]

    # 4. 'done' is valid even before any participant has been accepted.
    empty = DummyApp()
    with patch("builtins.input", side_effect=["done"]):
        empty.capture_participants_and_actions()

    assert empty.created == []
    assert empty.classified == []
    assert empty.model.participants() == []
    assert empty.questions == ["Who or what is involved?"]

    # 5. No yes/no gate is used anywhere in the manual participant loop.
    assert all("yes/no" not in question.casefold() for question in app.questions)
    assert all("yes/no" not in question.casefold() for question in first.questions)
    assert all("yes/no" not in question.casefold() for question in empty.questions)

    print("Participant flow test passed (5 UX checks).")


if __name__ == "__main__":
    main()
