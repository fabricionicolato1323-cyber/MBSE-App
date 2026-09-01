from __future__ import annotations

from unittest.mock import patch

from action_first_inline_flow import ActionFirstInlineCreationMixin
from minimal_input_policy import MinimalInputPolicyMixin
from minimal_input_web_patch import install_minimal_web_input_policy
from web_guided_flow import WebGuidedFlowMixin


install_minimal_web_input_policy()


class DummyModel:
    def __init__(self) -> None:
        self.names = {"p1": "Operator"}
        self.created: list[tuple] = []

    def name(self, node_id: str) -> str:
        return self.names[node_id]

    def participants(self) -> list[str]:
        return list(self.names)

    def expects_activity(self, node_id: str) -> bool:
        return True


class DummyWebApp(
    ActionFirstInlineCreationMixin,
    WebGuidedFlowMixin,
    MinimalInputPolicyMixin,
):
    def __init__(self) -> None:
        self.model = DummyModel()
        self.current_why = ""
        self.notices: list[str] = []
        self.llm = None

    def draw_question(self, *args, **kwargs) -> None:
        return None

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

    def activity_expectation_for(self, node_type: str, name: str) -> bool:
        return True

    def add_node(self, node_type: str, name: str, **attributes) -> str:
        node_id = f"p{len(self.model.names) + 1}"
        self.model.names[node_id] = name
        self.model.created.append((node_type, name, attributes))
        return node_id


def test_web_participant_entry_does_not_filter_wording() -> None:
    app = DummyWebApp()
    wording = "plataforma futura com sensor e qualquer outra palavra que o usuário quiser manter"
    with patch("builtins.input", return_value=wording):
        node_id = app._capture_one_participant()
    assert node_id == "p2"
    assert app.model.names[node_id] == wording
    assert not app.notices


def test_inline_action_entry_accepts_complex_wording_without_ai() -> None:
    app = DummyWebApp()
    wording = "Monitor traffic and trigger warning and coordinate passage"
    with patch("builtins.input", return_value=wording):
        value = app._capture_inline_action_text()
    assert value == wording
    assert not app.notices


def test_inline_action_interpretation_never_blocks_on_content() -> None:
    app = DummyWebApp()
    wording = "Install radar and call external service"
    frame = app._interpret_inline_action_text("p1", wording)
    assert frame["valid"] is True
    assert frame["solution_bias"] is False
    assert frame["clauses"][0]["activity_text"] == wording
