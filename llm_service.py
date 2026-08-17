from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from llama_cpp import Llama

from ontology import CONCEPT_GUIDANCE


VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "language": {
            "type": "string",
            "enum": ["English", "Non-English", "Language-neutral"],
        },
        "detected_concept": {
            "type": "string",
            "enum": [
                "OperationalCapability",
                "OperationalActor",
                "OperationalEntity",
                "OperationalActivity",
                "OperationalExchange",
                "CommunicationMean",
                "Other",
            ],
        },
        "normalized_value": {"type": "string"},
        "solution_bias": {"type": "boolean"},
        "reason": {"type": "string"},
        "suggestion": {"type": "string"},
    },
    "required": [
        "valid",
        "language",
        "detected_concept",
        "normalized_value",
        "solution_bias",
        "reason",
        "suggestion",
    ],
    "additionalProperties": False,
}


SYSTEM_VALIDATOR = """
You are a semantic gatekeeper for a guided operational-model builder based on
Arcadia Operational Analysis. The end user must never need Arcadia terminology.
You do not modify the graph. You only validate and normalize one candidate answer.

Internal concepts:
- OperationalCapability: an operational outcome or ability needed by stakeholders.
- OperationalActor: a human operational participant or human role.
- OperationalEntity: a non-human real-world participant or stakeholder in the operation.
- OperationalActivity: an action performed by a participant.
- OperationalExchange: information, material, request, or item exchanged between actions.
- CommunicationMean: an operational communication method between participants.

Rules:
1. Never invent facts.
2. Natural-language answers must be English. Proper names may be Language-neutral.
3. Stay in Operational Analysis. Reject premature software, hardware, architecture,
   component, algorithm, interface, or implementation choices when the same meaning
   can be stated as an operational need or action.
4. The system-of-interest must not be introduced as the future solution in Operational Analysis.
5. Actions should describe WHAT a participant does, preferably using a short verb phrase.
   Accept broad but meaningful action phrases. Do NOT reject an action merely because it is short or broad.
   Decisions, approvals, authorizations, commands, and engagements ARE operational actions when a participant performs them.
   Examples that MUST be treated as OperationalActivity when asked what a participant does:
   - 'Provide drone information'
   - 'Provide drone information such as position and velocity'
   - 'Decide to engage a countermeasure'
   - 'Engage a countermeasure'
   - 'Coordinate air traffic'
   - 'Maintain safe separation'
   Do not relabel such verb phrases as a goal, role description, or exchange just because their object describes an outcome or information.
6. Goals should describe outcomes, not product features or solution components.
7. Keep reasons short and user-friendly. Do not mention Arcadia terminology in the reason.
8. If invalid, give one simple English suggestion only when it preserves the user's intended meaning. Never invent a different fact.
9. normalized_value may fix grammar/capitalization but must preserve the same verb/object meaning.
10. Output JSON only using the supplied schema.
""".strip()


class LocalLLM:
    def __init__(
        self,
        model_path: str,
        n_ctx: int = 4096,
        n_threads: int | None = None,
        n_gpu_layers: int = 0,
        chat_format: str | None = None,
    ) -> None:
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(
                f"GGUF model not found: {path}\n"
                "Place the model in the models folder and update config.json if needed."
            )

        kwargs: dict[str, Any] = {
            "model_path": str(path),
            "n_ctx": n_ctx,
            "n_gpu_layers": n_gpu_layers,
            "verbose": False,
        }
        if n_threads is not None:
            kwargs["n_threads"] = n_threads
        if chat_format:
            kwargs["chat_format"] = chat_format

        self.llm = Llama(**kwargs)

    @staticmethod
    def _parse_json(content: str) -> dict:
        """Parse small-model JSON robustly without weakening the schema contract.

        Some local models occasionally place a raw newline or another control
        character inside a JSON string. Python's strict JSON parser rejects that
        even though the structure is otherwise usable. strict=False accepts these
        characters. We also strip accidental markdown fences and surrounding text.
        """
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]

        return json.loads(cleaned, strict=False)

    def _json_chat(self, messages: list[dict], schema: dict) -> dict:
        last_error: Exception | None = None

        # A small local model can occasionally produce malformed JSON even with a
        # schema. Retry once before surfacing an error to the user.
        for attempt in range(2):
            current_messages = list(messages)
            if attempt:
                current_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Return the answer again as one valid JSON object only. "
                            "Do not use markdown, comments, or literal line breaks inside JSON strings."
                        ),
                    }
                )

            response = self.llm.create_chat_completion(
                messages=current_messages,
                temperature=0,
                max_tokens=320,
                response_format={"type": "json_object", "schema": schema},
            )
            content = response["choices"][0]["message"]["content"]
            if not content:
                last_error = RuntimeError("The local LLM returned an empty response.")
                continue

            try:
                return self._parse_json(content)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                last_error = exc

        raise RuntimeError(f"The local model returned invalid structured data twice: {last_error}")

    def validate_candidate(self, candidate: str, expected_concept: str, context: str = "") -> dict:
        guidance = CONCEPT_GUIDANCE[expected_concept]
        prompt = f"""
Expected internal concept: {expected_concept}
Definition: {guidance['definition']}
Expected answer: {guidance['expected_format']}
Example: {guidance['example']}
Current context: {context or 'No additional context.'}
Candidate answer: {candidate}

Assess only this answer. Keep any user-facing reason simple and free of Arcadia jargon.
""".strip()
        return self._json_chat(
            [
                {"role": "system", "content": SYSTEM_VALIDATOR},
                {"role": "user", "content": prompt},
            ],
            VALIDATION_SCHEMA,
        )

    def validate_participant(self, candidate: str, context: str = "") -> dict:
        prompt = f"""
The user was asked to name one person, human role, organization, group, facility,
operational service, environment, or other real-world participant in an operation.

Classify the answer internally as:
- OperationalActor only when it clearly names a human person or human role.
- OperationalEntity when it names a non-human stakeholder or operational party,
  including an organization, authority, team, department, center, facility, or
  operational service.
- Other when it is not a stakeholder/participant or when it is clearly the future
  technical solution being designed.

Important classification examples:
- Air Traffic Controller -> OperationalActor
- Drone Traffic Controller -> OperationalActor
- Air Traffic Control -> OperationalEntity
- Drone Traffic Control -> OperationalEntity
- Airport Operations Center -> OperationalEntity
- Police Department -> OperationalEntity
- Drone Detection System -> Other when it is the solution being proposed

Do not reject a plausible stakeholder label merely because it is short or not a
complete sentence. For a participant label, valid should be true whenever the
classification is OperationalActor or OperationalEntity and there is no clear
solution bias or language violation.

Current context: {context or 'No additional context.'}
Candidate answer: {candidate}

Natural-language answers must be English. Proper names may be Language-neutral.
Do not expose Arcadia terminology in the reason.
""".strip()
        return self._json_chat(
            [
                {"role": "system", "content": SYSTEM_VALIDATOR},
                {"role": "user", "content": prompt},
            ],
            VALIDATION_SCHEMA,
        )
