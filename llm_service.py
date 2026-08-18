from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from llama_cpp import Llama

from fast_input import fast_operational_goal_result
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


# Keep this prompt compact: prompt-evaluation time is significant on CPU-only
# local models. The deterministic Python write barrier remains authoritative.
SYSTEM_VALIDATOR = """
You validate one answer for a guided Arcadia Operational Analysis assistant.
Do not modify the graph and do not invent facts.

Internal concepts:
- OperationalCapability: desired operational outcome/state.
- OperationalActor: human person, role, or human group.
- OperationalEntity: non-human real-world participant/context element.
- OperationalActivity: behavior performed by a participant.
- OperationalExchange: information/material/request/item exchanged between actions.
- CommunicationMean: real-world operational communication method.

Rules:
1. Natural-language answers must be English; proper names may be language-neutral.
2. Reject premature software/hardware/architecture/algorithm/implementation choices.
3. Judge meaning, not similarity to examples or fixed domain vocabulary.
4. A short unfamiliar verb phrase may still be a valid operational activity.
5. A goal is a desired outcome/state, not a future solution component.
6. Keep corrections semantically faithful; never invent a different action or fact.
7. Keep reasons short and user-friendly; do not expose Arcadia jargon.
8. Output JSON only using the supplied schema.
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
        max_tokens: int = 220,
    ) -> dict:
        last_error: Exception | None = None

        for attempt in range(2):
            current_messages = list(messages)
            if attempt:
                current_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Return one valid JSON object only. No markdown, comments, "
                            "or literal line breaks inside JSON strings."
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
                last_error = RuntimeError("The local LLM returned an empty response.")
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
Independent semantic recheck.
Expected concept: {expected_concept}
Definition: {guidance['definition']}
Context: {context or 'No additional context.'}
Candidate: {candidate}
First result: valid={first_result.get('valid')}, concept={first_result.get('detected_concept')}, solution_bias={first_result.get('solution_bias')}

Re-evaluate from scratch. The wording may use an unfamiliar but valid operational
verb or domain term. Reject only if the meaning genuinely fails the expected
concept, violates the language rule, or introduces a technical solution.
""".strip()

        return self._json_chat(
            [
                {"role": "system", "content": SYSTEM_VALIDATOR},
                {"role": "user", "content": prompt},
            ],
            VALIDATION_SCHEMA,
            max_tokens=180,
        )

    def validate_candidate(
        self,
        candidate: str,
        expected_concept: str,
        context: str = "",
    ) -> dict:
        # High-confidence operational goals do not need an LLM call. This removes
        # the exact false-negative/latency pattern seen with compact local models.
        if expected_concept == "OperationalCapability":
            fast_result = fast_operational_goal_result(candidate)
            if fast_result is not None:
                return fast_result

        guidance = CONCEPT_GUIDANCE[expected_concept]
        prompt = f"""
Expected concept: {expected_concept}
Definition: {guidance['definition']}
Expected form: {guidance['expected_format']}
Context: {context or 'No additional context.'}
Candidate: {candidate}

Assess only this answer from meaning. Do not require it to resemble an example.
""".strip()

        result = self._json_chat(
            [
                {"role": "system", "content": SYSTEM_VALIDATOR},
                {"role": "user", "content": prompt},
            ],
            VALIDATION_SCHEMA,
            max_tokens=180,
        )

        # Do not perform an expensive second LLM call for goals. Clear goal forms
        # were already handled by the deterministic fast path. Activity negatives
        # may still receive one independent semantic recheck.
        if (
            expected_concept == "OperationalActivity"
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
Classify one real-world operational element.
- OperationalActor: human person, role, or human group.
- OperationalEntity: non-human organization, group, facility, resource, place,
  area, environment, location, or external real-world party/context element.
- Other: neither of those, or clearly a proposed technical solution.

Classify from meaning without fixed profession/industry/asset vocabulary.
Context: {context or 'No additional context.'}
Candidate: {candidate}
""".strip()
        return self._json_chat(
            [
                {"role": "system", "content": SYSTEM_VALIDATOR},
                {"role": "user", "content": prompt},
            ],
            VALIDATION_SCHEMA,
            max_tokens=170,
        )
