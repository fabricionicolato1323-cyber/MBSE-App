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
- OperationalEntity: a non-human real-world participant or contextual element.
- OperationalActivity: an action performed by a participant.
- OperationalExchange: information, material, request, or item exchanged between actions.
- CommunicationMean: an operational communication method between participants.

General rules:
1. Never invent facts.
2. Natural-language answers must be English. Proper names may be Language-neutral.
3. Stay in Operational Analysis. Reject premature software, hardware, architecture,
   component, algorithm, interface, or implementation choices when the same meaning
   can be stated as an operational need or action.
4. Do not introduce the future system-of-interest as if it were an existing
   operational participant.
5. Validate actions semantically, not by matching a scenario-specific action list.
   A meaningful English verb phrase can be a valid OperationalActivity in any
   domain. Decisions, approvals, authorizations, observations, communication,
   coordination, information handling, service actions, and physical actions may
   all be valid when they describe what a participant does operationally.
6. Do not reject an action merely because it is short, broad, unfamiliar, or from
   a domain not represented in the prompt. Judge whether it expresses behavior.
7. Goals should describe an operational outcome or desired state, not a product
   feature or solution component. Judge the semantics rather than a fixed scenario.
8. Participant classification must be domain-independent. A human person, role, or
   human group is an OperationalActor. A non-human organization, group, facility,
   resource, place, area, environment, or other real-world contextual element is an
   OperationalEntity. A proposed technical solution is Other when it is not an
   existing operational participant.
9. Keep reasons short and user-friendly. Do not mention Arcadia terminology in the reason.
10. If invalid, give one simple English suggestion only when it preserves the user's
    intended meaning. Never invent a different fact.
11. normalized_value may fix grammar/capitalization but must preserve the same meaning.
12. Output JSON only using the supplied schema.

The rules above are intentionally domain-neutral. Do not assume any specific
industry, mission, organization, asset type, profession, or action vocabulary.
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
        """Parse small-model JSON robustly without weakening the schema contract."""
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]

        return json.loads(cleaned, strict=False)

    def _json_chat(
        self,
        messages: list[dict],
        schema: dict,
        *,
        max_tokens: int = 320,
    ) -> dict:
        last_error: Exception | None = None

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
                max_tokens=max_tokens,
                response_format={"type": "json_object", "schema": schema},
            )
            content = response["choices"][0]["message"]["content"]
            if not content:
                last_error = RuntimeError(
                    "The local LLM returned an empty response."
                )
                continue

            try:
                return self._parse_json(content)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                last_error = exc

        raise RuntimeError(
            f"The local model returned invalid structured data twice: {last_error}"
        )

    @staticmethod
    def _needs_semantic_recheck(result: dict, expected_concept: str) -> bool:
        """Decide whether a compact-model negative deserves one neutral second look."""
        return (
            not bool(result.get("valid", False))
            or result.get("detected_concept") != expected_concept
            or bool(result.get("solution_bias", False))
        )

    def _semantic_recheck(
        self,
        candidate: str,
        expected_concept: str,
        context: str,
        first_result: dict,
    ) -> dict:
        guidance = CONCEPT_GUIDANCE[expected_concept]
        prompt = f"""
Perform an independent second semantic check.

Expected internal concept: {expected_concept}
Definition: {guidance['definition']}
Expected answer form: {guidance['expected_format']}
Current context: {context or 'No additional context.'}
Candidate answer: {candidate}

The first check returned:
- valid: {first_result.get('valid')}
- detected concept: {first_result.get('detected_concept')}
- solution bias: {first_result.get('solution_bias')}
- reason: {first_result.get('reason', '')}

Do not defend the first answer. Re-evaluate from scratch. The candidate may come
from any application domain and may use an unfamiliar but valid verb, role, asset,
resource, organization, or place name. Do not require it to match any memorized
example or fixed vocabulary. Reject it only when its meaning genuinely fails the
expected concept, is non-English where English is required, or introduces a
premature technical solution.
""".strip()

        return self._json_chat(
            [
                {"role": "system", "content": SYSTEM_VALIDATOR},
                {"role": "user", "content": prompt},
            ],
            VALIDATION_SCHEMA,
        )

    def validate_candidate(
        self,
        candidate: str,
        expected_concept: str,
        context: str = "",
    ) -> dict:
        guidance = CONCEPT_GUIDANCE[expected_concept]
        prompt = f"""
Expected internal concept: {expected_concept}
Definition: {guidance['definition']}
Expected answer: {guidance['expected_format']}
Generic form example: {guidance['example']}
Current context: {context or 'No additional context.'}
Candidate answer: {candidate}

Assess only this answer using the concept definition and general rules. Do not
require the candidate to resemble the example. Keep any user-facing reason simple
and free of Arcadia jargon.
""".strip()

        result = self._json_chat(
            [
                {"role": "system", "content": SYSTEM_VALIDATOR},
                {"role": "user", "content": prompt},
            ],
            VALIDATION_SCHEMA,
        )

        if (
            expected_concept in {"OperationalActivity", "OperationalCapability"}
            and self._needs_semantic_recheck(result, expected_concept)
        ):
            second = self._semantic_recheck(
                candidate,
                expected_concept,
                context,
                result,
            )
            if (
                second.get("valid", False)
                and second.get("detected_concept") == expected_concept
                and not second.get("solution_bias", False)
            ):
                return second

        return result

    def validate_participant(
        self,
        candidate: str,
        context: str = "",
    ) -> dict:
        prompt = f"""
The user was asked to name one real-world element involved in an operation.

Classify the answer internally as:
- OperationalActor only when it clearly names a human person, human role, or human group.
- OperationalEntity when it names a non-human real-world participant or contextual
  element such as an organization, group, facility, resource, place, area,
  environment, location, or external party.
- Other when it is neither of those, or when it is clearly a proposed technical
  solution rather than an existing real-world participant/context element.

Do not use a fixed vocabulary of professions, industries, assets, places, or
scenario names. Classify from meaning. Do not reject a plausible short label merely
because it is not a complete sentence or because its domain is unfamiliar.

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
