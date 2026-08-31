from __future__ import annotations

import unittest

from participant_classification_simple import SimplifiedParticipantClassificationMixin


class DummyClassifier(SimplifiedParticipantClassificationMixin):
    def __init__(self, choice: str) -> None:
        self.choice = choice
        self.seen_choices: list[tuple[str, str]] = []
        self.question = ""

    def ask_choice(self, question, choices, why, extra_lines=None):
        self.question = question
        self.seen_choices = list(choices)
        return self.choice


class SimplifiedParticipantClassificationTests(unittest.TestCase):
    def test_only_two_user_visible_classifications_are_offered(self) -> None:
        app = DummyClassifier("actor")
        concept, name, attributes = app.confirm_participant_classification("  Operator  ")

        self.assertEqual(app.question, "How should this participant be classified?")
        self.assertEqual(
            [key for key, _ in app.seen_choices],
            ["actor", "entity"],
        )
        self.assertIn("Actor / role", app.seen_choices[0][1])
        self.assertIn("Entity / context", app.seen_choices[1][1])
        self.assertEqual(concept, "OperationalActor")
        self.assertEqual(name, "Operator")
        self.assertEqual(attributes["nature"], "human_individual")

    def test_entity_choice_maps_to_operational_entity_without_extra_question(self) -> None:
        app = DummyClassifier("entity")
        concept, name, attributes = app.confirm_participant_classification("Station")

        self.assertEqual(concept, "OperationalEntity")
        self.assertEqual(name, "Station")
        self.assertEqual(len(app.seen_choices), 2)
        self.assertEqual(attributes["classification_source"], "user_choice")
        self.assertEqual(attributes["confirmed_by"], "user")


if __name__ == "__main__":
    unittest.main()
