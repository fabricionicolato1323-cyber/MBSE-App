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


# Participant classification uses a smaller schema because generating fields that
# are irrelevant to this decision costs noticeable time on CPU-only local models.
PARTICIPANT_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {
            "type": "string",
            "enum": ["English", "Non-English", "Language-neutral"],
        },
        "detected_concept": {
            "type": "string",
            "enum": ["OperationalActor", "OperationalEntity", "Other"],
        },
        "normalized_value": {"type": "string"},
        "solution_bias": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": [
        "language",
        "detected_concept",
        "normalized_value",
        "solution_bias",
        "reason",
    ],
    "additionalProperties": False,
}


KNOWLEDGE_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "coverage": {"type": "string", "enum": ["SUPPORTED", "NOT_FOUND"]},
        "answer": {"type": "string"},
        "claim_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["coverage", "answer", "claim_ids"],
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


PARTICIPANT_SYSTEM = """
Classify one noun phrase for an operational-model builder.

OperationalActor = a human person, profession, occupation, job title, human role,
or human group. A role is valid even when it is not a named individual.
OperationalEntity = a non-human real-world organization, group, facility, resource,
place, area, environment, location, or external party/context element.
Other = neither of those, or clearly a proposed technical solution.

Important rules:
- A profession/job title is a human role, so classify it as OperationalActor.
- Do NOT reject something because it was not mentioned earlier or because the
  current goal/context does not explicitly name it. This step classifies type only.
- Do not require a named physical instance; operational roles are legitimate.
- Classify from meaning without fixed profession, industry, or asset vocabulary.
- Never invent or rewrite the meaning.
- Output JSON only.
""".strip()


KNOWLEDGE_ANSWER_SYSTEM = """
You verbalize evidence retrieved from an Arcadia Operational Analysis knowledge graph.

Source policy:
- Use only facts explicitly present in EVIDENCE.
- Do not add facts from memory, training data, or general Arcadia knowledge.
- Answer in clear English even when evidence text is Portuguese.
- Preserve the distinction between ArcadiaReference, ModelingRecommendation,
  ApplicationPolicy, and LinguisticHeuristic.
- Cite only claim_id values present in EVIDENCE.
- If EVIDENCE does not answer the question, return coverage NOT_FOUND.
- Do not suggest or modify any element in the user's operational model.
- Output JSON only using the supplied schema.
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
        # Context is intentionally not sent to the classifier. At this point the
        # user is explicitly introducing a possible participant/context element;
        # classification must not reject it merely because it was absent from the
        # goal or previous model state.
        prompt = f"Candidate: {candidate}\nClassify its type only."
        compact = self._json_chat(
            [
                {"role": "system", "content": PARTICIPANT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            PARTICIPANT_SCHEMA,
            max_tokens=90,
        )

        detected = compact.get("detected_concept", "Other")
        solution_bias = bool(compact.get("solution_bias", False))
        reason = str(compact.get("reason", ""))

        # Generic repair for a compact-model contradiction such as:
        # "This is a profession, not a participant." In this ontology a
        # profession/job title/human role is exactly an OperationalActor.
        reason_lower = reason.casefold()
        role_cues = (
            "profession",
            "occupation",
            "job title",
            "human role",
            "professional role",
        )
        if (
            detected == "Other"
            and not solution_bias
            and any(cue in reason_lower for cue in role_cues)
        ):
            detected = "OperationalActor"
            reason = ""

        normalized = str(compact.get("normalized_value") or candidate).strip()
        return {
            "valid": detected in {"OperationalActor", "OperationalEntity"}
            and not solution_bias,
            "language": compact.get("language", "Language-neutral"),
            "detected_concept": detected,
            "normalized_value": normalized,
            "solution_bias": solution_bias,
            "reason": reason,
            "suggestion": "",
        }

    def answer_from_knowledge(
        self,
        question: str,
        evidence: list[dict],
    ) -> dict:
        """Verbalize only graph-retrieved claims; never use model memory as a source."""
        prompt = (
            f"QUESTION\n{question}\n\n"
            f"EVIDENCE\n{json.dumps(evidence, ensure_ascii=False, indent=2)}"
        )
        return self._json_chat(
            [
                {"role": "system", "content": KNOWLEDGE_ANSWER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            KNOWLEDGE_ANSWER_SCHEMA,
            max_tokens=420,
        )
