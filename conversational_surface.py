from __future__ import annotations

import re


class ConversationalSurfaceMixin:
    """Use an active local LLM only to naturalize already-decided questions.

    The semantic process remains authoritative outside the LLM. When ``self.llm``
    is ``None`` the original question is rendered unchanged. When a local model is
    active, it may rephrase the question for conversational flow, but it cannot
    change choices, write model facts, select the next step, or alter validation.
    """

    _allow_llm_semantic_parsing = False

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
        """Do not use the LLM as a semantic candidate extractor.

        Participant discovery remains in the normal guided/KG flow. This deliberate
        no-op prevents activating conversational AI from changing model semantics.
        """
        del goals
