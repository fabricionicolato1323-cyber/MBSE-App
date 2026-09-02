from __future__ import annotations

import unittest

from conversational_surface import ConversationalSurfaceMixin
from llm_conversation import install_conversational_llm_support
from llm_service import OllamaLLM


class RecorderBase:
    def __init__(self, llm=None) -> None:
        self.llm = llm
        self.rendered_question = ""
        self.rendered_explanation = ""

    def draw_question(
        self,
        question: str,
        explanation: str = "",
        example: str = "",
        expected_structure: str = "",
        extra_lines=None,
    ) -> None:
        del example, expected_structure, extra_lines
        self.rendered_question = question
        self.rendered_explanation = explanation


class SurfaceApp(ConversationalSurfaceMixin, RecorderBase):
    pass


class FakeConversationLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def conversationalize_question(self, question: str, *, explanation: str = "") -> str:
        self.calls.append((question, explanation))
        return self.response


class FailingConversationLLM:
    def conversationalize_question(self, question: str, *, explanation: str = "") -> str:
        raise RuntimeError("offline")


class ConversationalSurfaceTests(unittest.TestCase):
    def test_llm_off_preserves_normal_question_exactly(self) -> None:
        app = SurfaceApp(llm=None)
        app.draw_question("Who or what is involved?", explanation="Name one participant.")
        self.assertEqual(app.rendered_question, "Who or what is involved?")

    def test_active_llm_may_only_rephrase_question(self) -> None:
        llm = FakeConversationLLM("Who else is part of this operation?")
        app = SurfaceApp(llm=llm)
        app.draw_question("Who or what else is involved?", explanation="Name one participant.")
        self.assertEqual(app.rendered_question, "Who else is part of this operation?")
        self.assertEqual(app.rendered_explanation, "Name one participant.")
        self.assertEqual(len(llm.calls), 1)

    def test_repeated_question_uses_cache(self) -> None:
        llm = FakeConversationLLM("Who else is involved in the operation?")
        app = SurfaceApp(llm=llm)
        for _ in range(2):
            app.draw_question("Who or what else is involved?", explanation="Name one participant.")
        self.assertEqual(len(llm.calls), 1)

    def test_quoted_model_name_must_be_preserved(self) -> None:
        llm = FakeConversationLLM("Who performs this role?")
        app = SurfaceApp(llm=llm)
        original = "Who or what performs the 'Level Crossing Manager' role?"
        app.draw_question(original)
        self.assertEqual(app.rendered_question, original)

    def test_yes_no_contract_cannot_be_removed(self) -> None:
        llm = FakeConversationLLM("Is there another important goal?")
        app = SurfaceApp(llm=llm)
        original = "Is there another important goal? (yes/no)"
        app.draw_question(original)
        self.assertEqual(app.rendered_question, original)

    def test_llm_failure_falls_back_to_normal_question(self) -> None:
        app = SurfaceApp(llm=FailingConversationLLM())
        original = "What is the main goal?"
        app.draw_question(original)
        self.assertEqual(app.rendered_question, original)

    def test_goal_candidate_extraction_is_disabled_in_conversational_mode(self) -> None:
        app = SurfaceApp(llm=FakeConversationLLM("Unused"))
        self.assertIsNone(app.capture_goal_candidates([("goal:1", "Keep crossing safe")]))

    def test_ollama_client_receives_conversational_extension(self) -> None:
        install_conversational_llm_support()
        self.assertTrue(callable(getattr(OllamaLLM, "conversationalize_question", None)))


if __name__ == "__main__":
    unittest.main()
