from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

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


SYSTEM_VALIDATOR = """
You provide advisory semantic validation for a guided Arcadia Operational
Analysis assistant. Do not modify the graph and do not invent facts. The user is
the final authority for model quality.

Internal concepts:
- OperationalCapability: desired operational outcome/state.
- OperationalActor: one indivisible human person or human role.
- OperationalEntity: a collective or non-human real-world participant/context.
- OperationalActivity: behavior performed by a participant.
- OperationalExchange: information/material/request/item exchanged between actions.
- CommunicationMean: real-world operational communication method.

Rules:
1. Natural-language answers must be English; proper names may be language-neutral.
2. Flag premature software/hardware/architecture/algorithm choices.
3. Judge meaning, not similarity to examples or fixed domain vocabulary.
4. A short unfamiliar verb phrase may still be a valid operational activity.
5. A goal is a desired outcome/state, not a future solution component.
6. Never invent or silently correct a different fact.
7. Keep reasons short and user-friendly.
8. Output JSON only using the supplied schema.
""".strip()


PARTICIPANT_SYSTEM = """
Provide an advisory classification for one noun phrase.

OperationalActor = one human person, profession, occupation, job title, or
indivisible human role. OperationalEntity = a collective, organization,
organizational unit, team, existing external technical participant, facility,
operational service, population, community, or environmental participant.
Other = neither of those, a communication/information/location item that does
not participate operationally, or a proposed solution.

Important rules:
- A profession or job title is an OperationalActor.
- A singular human role label is an OperationalActor; a plural phrase naming
  several people or role-holders is an OperationalEntity.
- A team, crew, staff, department, or organization is an OperationalEntity.
- Do not require a named individual; a human role is legitimate.
- Do not reject an existing external technical participant merely because it is
  technical. Do flag a proposed or future System of Interest.
- Classify from meaning without inventing facts.
- The result is only advice; the user will make the final decision.
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


class OllamaError(RuntimeError):
    pass


class ModelSelectionError(OllamaError):
    pass


@dataclass(frozen=True)
class ResponseMetrics:
    client_seconds: float
    ollama_seconds: float | None = None
    load_seconds: float | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None


def _nanoseconds_to_seconds(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return float(value) / 1_000_000_000


class OllamaLLM:
    """Small Ollama HTTP client with structured output and response telemetry."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str | None = None,
        model_env: str = "MBSE_OLLAMA_MODEL",
        timeout_seconds: float = 120,
        keep_alive: str | int | None = None,
        num_ctx: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url.endswith("/api"):
            self.base_url = self.base_url[:-4]
        self.timeout_seconds = timeout_seconds
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self.metrics: list[ResponseMetrics] = []

        configured_model = str(model or os.getenv(model_env, "")).strip()
        installed = self.list_models()
        self.model = self._resolve_model(configured_model, installed, model_env)

    @staticmethod
    def _resolve_model(
        configured_model: str,
        installed_models: list[str],
        model_env: str,
    ) -> str:
        if configured_model:
            if configured_model not in installed_models:
                available = ", ".join(installed_models) or "none"
                raise ModelSelectionError(
                    f"Configured Ollama model '{configured_model}' is not installed. "
                    f"Available models: {available}."
                )
            return configured_model

        if len(installed_models) == 1:
            return installed_models[0]
        if not installed_models:
            raise ModelSelectionError(
                "No Ollama model is installed. Install one, then set "
                f"{model_env} or config.json."
            )

        available = ", ".join(installed_models)
        raise ModelSelectionError(
            "More than one Ollama model is installed and no model was selected. "
            f"Set {model_env} or config.json. Available models: {available}."
        )

    def _request(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        method = "GET"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(
                f"Ollama HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}: {exc}"
            ) from exc

        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned invalid JSON.") from exc
        if not isinstance(decoded, dict):
            raise OllamaError("Ollama returned an unexpected response shape.")
        return decoded

    def list_models(self) -> list[str]:
        response = self._request("/api/tags")
        names: list[str] = []
        for item in response.get("models", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("model") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    @staticmethod
    def _parse_json(content: str) -> dict:
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
        parsed = json.loads(cleaned, strict=False)
        if not isinstance(parsed, dict):
            raise ValueError("Expected one JSON object.")
        return parsed

    def metric_count(self) -> int:
        return len(self.metrics)

    def timing_summary_since(self, start_index: int) -> str:
        items = self.metrics[start_index:]
        if not items:
            return "No Ollama response was required."
        wall = sum(item.client_seconds for item in items)
        ollama_values = [
            item.ollama_seconds
            for item in items
            if item.ollama_seconds is not None
        ]
        ollama_text = (
            f" | Ollama: {sum(ollama_values):.2f} s"
            if ollama_values
            else ""
        )
        return (
            f"Ollama responses: {len(items)} | client time: {wall:.2f} s"
            f"{ollama_text}"
        )

    def _record_metrics(self, response: dict[str, Any], elapsed: float) -> None:
        self.metrics.append(
            ResponseMetrics(
                client_seconds=elapsed,
                ollama_seconds=_nanoseconds_to_seconds(
                    response.get("total_duration")
                ),
                load_seconds=_nanoseconds_to_seconds(
                    response.get("load_duration")
                ),
                prompt_tokens=(
                    int(response["prompt_eval_count"])
                    if isinstance(response.get("prompt_eval_count"), int)
                    else None
                ),
                output_tokens=(
                    int(response["eval_count"])
                    if isinstance(response.get("eval_count"), int)
                    else None
                ),
            )
        )

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

            options: dict[str, Any] = {
                "temperature": 0,
                "num_predict": max_tokens,
            }
            if self.num_ctx is not None:
                options["num_ctx"] = self.num_ctx

            payload: dict[str, Any] = {
                "model": self.model,
                "messages": current_messages,
                "stream": False,
                "format": schema,
                "options": options,
            }
            if self.keep_alive is not None:
                payload["keep_alive"] = self.keep_alive

            started = time.perf_counter()
            response = self._request("/api/chat", payload)
            elapsed = time.perf_counter() - started
            self._record_metrics(response, elapsed)

            message = response.get("message", {})
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                last_error = OllamaError("Ollama returned an empty response.")
                continue

            try:
                return self._parse_json(content)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                last_error = exc

        raise OllamaError(
            f"Ollama returned invalid structured data twice: {last_error}"
        )

    @staticmethod
    def _needs_semantic_recheck(result: dict, expected_concept: str) -> bool:
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

Re-evaluate from scratch. Reject only when the meaning genuinely fails the
expected concept, violates the language rule, or introduces a technical solution.
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
        del context
        prompt = f"Candidate: {candidate}\nClassify its type only."
        compact = self._json_chat(
            [
                {"role": "system", "content": PARTICIPANT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            PARTICIPANT_SCHEMA,
            max_tokens=100,
        )
        detected = compact.get("detected_concept", "Other")
        solution_bias = bool(compact.get("solution_bias", False))
        normalized = str(compact.get("normalized_value") or candidate).strip()
        return {
            "valid": detected in {"OperationalActor", "OperationalEntity"}
            and not solution_bias,
            "language": compact.get("language", "Language-neutral"),
            "detected_concept": detected,
            "normalized_value": normalized,
            "solution_bias": solution_bias,
            "reason": str(compact.get("reason", "")),
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
