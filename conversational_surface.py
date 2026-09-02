from __future__ import annotations

import re

from semantic_frames import looks_structurally_complex, parse_simple_activity_frame
from terminal_ui import EXPECTED_STRUCTURES
from validator import normalize_whitespace


class ConversationalSurfaceMixin:
    """Use an active local LLM only to naturalize already-decided questions.

    The semantic process remains authoritative outside the LLM. When ``self.llm``
    is ``None`` the original question is rendered unchanged. When a local model is
    active, it may rephrase the question for conversational flow, but it cannot
    change choices, write model facts, select the next step, extract candidates,
    classify participants, or decompose activities.
    """

    @staticmethod
    def _quoted_literals(value: str) -> tuple[str, ...]:
        return tuple(
            match.group(1) or match.group(2)
            for match in re.finditer(r"'([^']+)'|\"([^\"]+)\"", value)
        )

    @classmethod
    def _safe_conversational_question(cls, original: str, candidate: object) -> str:
        text = str(candidate or "").strip()
        if not text or len(text) > 280 or "\n" in text:
            return original
        if any(literal not in text for literal in cls._quoted_literals(original)):
            return original

        normalized_original = original.casefold()
        normalized_candidate = text.casefold()
        if "yes/no" in normalized_original and not (
            "yes" in normalized_candidate and "no" in normalized_candidate
        ):
            return original
        return text

    def _conversational_question(self, question: str, explanation: str) -> str:
        llm = getattr(self, "llm", None)
        verbalize = getattr(llm, "conversationalize_question", None)
        if not callable(verbalize):
            return question

        cache = getattr(self, "_conversation_surface_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._conversation_surface_cache = cache
        key = (question, explanation)
        if key in cache:
            return cache[key]

        try:
            candidate = verbalize(question, explanation=explanation)
        except Exception:
            # Conversational polish is optional. Any local-model failure must leave
            # the deterministic/KG-driven question intact and keep the flow moving.
            candidate = question

        rendered = self._safe_conversational_question(question, candidate)
        if len(cache) >= 128:
            cache.clear()
        cache[key] = rendered
        return rendered

    def draw_question(
        self,
        question: str,
        explanation: str = "",
        example: str = "",
        expected_structure: str = "",
        extra_lines: list[str] | None = None,
    ) -> None:
        rendered_question = (
            self._conversational_question(question, explanation)
            if getattr(self, "llm", None) is not None
            else question
        )
        super().draw_question(
            rendered_question,
            explanation=explanation,
            example=example,
            expected_structure=expected_structure,
            extra_lines=extra_lines,
        )

    def capture_goal_candidates(self, goals: list[tuple[str, str]]) -> None:
        """Never use an active LLM as a semantic candidate extractor."""
        del goals

    def ask_activity_frames(self, participant_id: str) -> tuple[str, dict]:
        """Keep activity interpretation deterministic when conversational AI is on.

        Simple sentences use the existing deterministic parser. Complex sentences
        are preserved as one user-authored activity through the minimal structural
        fallback; the LLM is never asked to interpret or decompose their meaning.
        """
        participant_name = self.model.name(participant_id)
        self.current_why = (
            "The action structure identifies who performs the behavior while the "
            "user remains authoritative for its meaning."
        )

        while True:
            self.draw_question(
                f"What does {participant_name} do?",
                explanation=(
                    "Describe one action or a natural sentence. The conversational "
                    "AI may rephrase this question, but it does not interpret your answer."
                ),
                expected_structure=EXPECTED_STRUCTURES["OperationalActivity"],
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available in this step.")
                continue

            normalized = normalize_whitespace(value)
            if not normalized:
                self.add_notice("Please enter an activity.")
                continue

            frame_result = None
            if not looks_structurally_complex(normalized):
                frame_result = parse_simple_activity_frame(
                    normalized,
                    default_subject=participant_name,
                )

            return normalized, self._sanitize_activity_frame(
                frame_result,
                normalized,
                participant_name,
            )
