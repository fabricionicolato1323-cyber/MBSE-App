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
        for line in extra_lines or []:
            print(line)

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


def capture(callback):
    output = StringIO()
    with redirect_stdout(output):
        result = callback()
    return output.getvalue(), result


def test_internal_classification_labels_are_not_exposed_in_buttons():
    app = DummyWebApp()
    output, _ = capture(
        lambda: app.ask_choice(
            "How should this candidate be classified?",
            [
                ("actor", "Classify as Operational Actor"),
                ("entity", "Classify as Operational Entity"),
            ],
            "test",
            extra_lines=[
                "  Candidate: Visitor",
                "  Suggestion: OperationalActor",
                "  Evidence: insufficient",
            ],
        )
    )
    interaction = decode_latest_interaction(output)
    assert [item["label"] for item in interaction["choices"]] == [
        "Person / role",
        "Organization, group, facility or other participant",
    ]
    assert "Evidence:" not in output
    assert "Suggestion:" not in output


def test_yes_no_remains_clickable_contract():
    app = DummyWebApp()
    output, _ = capture(lambda: app.ask_yes_no("Continue?", "test"))
    interaction = decode_latest_interaction(output)
    assert interaction["mode"] == "yes_no"
    assert [item["value"] for item in interaction["choices"]] == ["yes", "no"]
