from __future__ import annotations

from llm_service import OllamaLLM


CONVERSATION_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
    },
    "required": ["question"],
    "additionalProperties": False,
}


CONVERSATION_SYSTEM = """
You are only the conversational surface of a guided modeling application.
The application and its Knowledge Graph have already decided WHAT must be asked.
Your only job is to say the supplied question in concise, natural English.

Hard rules:
1. Preserve the exact semantic intent of AUTHORITATIVE QUESTION.
2. Do not classify, infer, recommend, validate, rank, or choose anything.
3. Do not add new facts, assumptions, examples, alternatives, or follow-up questions.
4. Do not remove explicit answer constraints such as yes/no.
5. Preserve quoted names and labels exactly.
6. Do not mention internal ontology, Knowledge Graph, Arcadia, rules, or AI unless
   those words are already present in the authoritative question.
7. Return one question only, preferably one sentence and under 40 words.
8. Output JSON only using the supplied schema.
""".strip()


def install_conversational_llm_support() -> None:
    """Add question verbalization without changing Ollama's semantic APIs."""
    cls = OllamaLLM
    if getattr(cls, "_conversational_surface_installed", False):
        return

    def conversationalize_question(
        self: OllamaLLM,
        question: str,
        *,
        explanation: str = "",
    ) -> str:
        prompt = (
            f"AUTHORITATIVE QUESTION\n{question.strip()}\n\n"
            f"READ-ONLY CONTEXT\n{explanation.strip() or 'None.'}\n\n"
            "Rewrite only the authoritative question."
        )
        result = self._json_chat(  # noqa: SLF001 - controlled extension of local client
            [
                {"role": "system", "content": CONVERSATION_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            CONVERSATION_SCHEMA,
            max_tokens=90,
        )
        return str(result.get("question") or "").strip()

    cls.conversationalize_question = conversationalize_question
    cls._conversational_surface_installed = True
