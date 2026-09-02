from contextlib import redirect_stdout
from io import StringIO

from web_protocol import decode_latest_interaction
from web_worker import WebInteractionMixin


class DummyBase:
    def draw_question(
        self,
        question,
        explanation="",
        example="",
        expected_structure="",
        extra_lines=None,
    ):
        print(question)

    def ask_yes_no(self, question, why):
        self.draw_question(f"{question} (yes/no)")
        return True

    def ask_choice(self, question, choices, why, extra_lines=None):
        self.draw_question(question, extra_lines=extra_lines)
        return choices[0][0]

    def ask_number(self, question, node_ids, label, why):
        self.draw_question(question)
        return node_ids[0]


class DummyWebApp(WebInteractionMixin, DummyBase):
    pass


def capture_interaction(callback):
    output = StringIO()
    with redirect_stdout(output):
        callback()
    return decode_latest_interaction(output.getvalue())


def test_yes_no_helper_emits_explicit_binary_interaction():
    app = DummyWebApp()
    interaction = capture_interaction(
        lambda: app.ask_yes_no("Continue?", "test")
    )
    assert interaction["mode"] == "yes_no"
    assert [item["value"] for item in interaction["choices"]] == ["yes", "no"]


def test_choice_helper_emits_clickable_number_values():
    app = DummyWebApp()
    interaction = capture_interaction(
        lambda: app.ask_choice(
            "Choose one",
            [("internal-a", "First option"), ("internal-b", "Second option")],
            "test",
        )
    )
    assert interaction == {
        "mode": "choice",
        "choices": [
            {"label": "First option", "value": "1"},
            {"label": "Second option", "value": "2"},
        ],
    }


def test_number_helper_emits_clickable_labels_not_typed_numbers():
    app = DummyWebApp()
    labels = {"a": "First action", "b": "Second action"}
    interaction = capture_interaction(
        lambda: app.ask_number(
            "Which action receives it?",
            ["a", "b"],
            lambda node_id: labels[node_id],
            "test",
        )
    )
    assert interaction == {
        "mode": "choice",
        "choices": [
            {"label": "First action", "value": "1"},
            {"label": "Second action", "value": "2"},
        ],
    }


def test_open_question_emits_free_text_interaction():
    app = DummyWebApp()
    interaction = capture_interaction(
        lambda: app.draw_question("Describe one item")
    )
    assert interaction == {"mode": "free_text", "choices": []}
