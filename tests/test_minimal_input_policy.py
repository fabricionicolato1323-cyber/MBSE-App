from __future__ import annotations

from unittest.mock import patch

from minimal_input_policy import MinimalInputPolicyMixin


class DummyModel:
    def __init__(self) -> None:
        self._names = {"p1": "Operator"}

    def name(self, node_id: str) -> str:
        return self._names[node_id]

    def participants(self) -> list[str]:
        return list(self._names)

    def short_context(self) -> str:
        return ""


class DummyApp(MinimalInputPolicyMixin):
    def __init__(self) -> None:
        self.model = DummyModel()
        self.current_why = ""
        self.notices: list[str] = []
        self.questions: list[str] = []
        self.llm = None

    def draw_question(self, question: str, *args, **kwargs) -> None:
        self.questions.append(question)

    def command(self, value: str) -> bool:
        return False

    def add_notice(self, message: str) -> None:
        self.notices.append(message)

    def confirm_participant_classification(self, value: str):
        return (
            "OperationalActor",
            value,
            {
                "nature": "human_individual",
                "status": "confirmed",
                "confirmed_by": "user",
            },
        )


def test_free_text_is_not_blocked_by_wording_or_semantic_guess() -> None:
    app = DummyApp()
    with patch("builtins.input", return_value="Install radar sensor"):
        result = app.ask_validated(
            "What is the goal?",
            "",
            expected_concept="OperationalCapability",
        )
    assert result == "Install radar sensor"
    assert not app.notices


def test_non_english_or_misspelled_wording_is_not_a_write_barrier() -> None:
    app = DummyApp()
    with patch("builtins.input", return_value="detectar ameaça"):
        result = app.ask_validated(
            "What happens?",
            "",
            expected_concept="OperationalActivity",
        )
    assert result == "detectar ameaça"
    assert not app.notices


def test_only_missing_structure_reasks_for_free_text() -> None:
    app = DummyApp()
    with patch("builtins.input", side_effect=["   ", "Any wording"]):
        result = app.ask_validated(
            "Enter a value",
            "",
            expected_concept="OperationalExchange",
        )
    assert result == "Any wording"
    assert app.notices == ["Please enter a value."]


def test_participant_name_is_not_semantically_filtered() -> None:
    app = DummyApp()
    with patch("builtins.input", return_value="Future AI sensor platform"):
        concept, name, _ = app.ask_participant()
    assert concept == "OperationalActor"
    assert name == "Future AI sensor platform"
    assert not app.notices


def test_complex_activity_does_not_require_ai_or_rewrite() -> None:
    app = DummyApp()
    text = "Monitor traffic and trigger the crossing warning"
    with patch("builtins.input", return_value=text):
        source, frame = app.ask_activity_frames("p1")
    assert source == text
    assert frame["valid"] is True
    assert frame["solution_bias"] is False
    assert len(frame["clauses"]) == 1
    assert frame["clauses"][0]["activity_text"] == text
    assert frame["clauses"][0]["subjects"] == ["Operator"]
    assert not app.notices
