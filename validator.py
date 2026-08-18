from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

try:
    from langdetect import DetectorFactory, LangDetectException, detect

    DetectorFactory.seed = 0
    _HAS_LANGDETECT = True
except ImportError:
    LangDetectException = Exception
    detect = None
    _HAS_LANGDETECT = False

from ontology import CONCEPT_GUIDANCE, SOLUTION_BIAS_TERMS


@dataclass
class ValidationResult:
    accepted: bool
    normalized_value: str = ""
    detected_concept: str = ""
    reason: str = ""
    suggestion: str = ""


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def deterministic_english_check(value: str) -> Optional[bool]:
    """Use statistical language detection only when the phrase is long enough."""
    words = re.findall(r"[A-Za-zÀ-ÿ]+", value)
    letters = sum(len(word) for word in words)
    if len(words) < 10 or letters < 60:
        return None
    if not _HAS_LANGDETECT or detect is None:
        return None
    try:
        return detect(value) == "en"
    except LangDetectException:
        return None


# These terms describe implementation categories, not application domains.
TECHNICAL_SOLUTION_WORDS = {
    "system",
    "software",
    "application",
    "platform",
    "algorithm",
    "database",
    "microservice",
    "sensor network",
    "api",
}


# High-confidence language markers only. There is deliberately no operational
# domain vocabulary here.
NON_ENGLISH_MARKERS = {
    # Portuguese
    "o", "a", "os", "as", "de", "da", "do", "das", "dos", "para", "com", "sem",
    "e", "ou", "que", "como", "avaliar", "fornecer", "informar", "controlar",
    "manter", "proteger", "reduzir", "garantir", "melhorar",
    "informação", "informações", "posição", "velocidade",
    # German
    "der", "die", "das", "den", "dem", "des", "und", "oder", "mit", "ohne", "für",
    "über", "melden", "bereitstellen", "steuern", "überwachen", "halten", "schützen",
    # Spanish / French
    "el", "la", "los", "las", "y", "con", "sin", "proporcionar", "mantener",
    "le", "les", "et", "avec", "sans", "fournir", "maintenir", "protéger",
}


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-zà-ÿ]+", value.casefold())


def _token_set(value: str) -> set[str]:
    return set(_tokens(value))


def obvious_non_english_short_text(value: str) -> bool:
    tokens = _token_set(value)
    if not tokens:
        return False
    has_diacritic = bool(re.search(r"[^\x00-\x7F]", value))
    marker_hits = tokens & NON_ENGLISH_MARKERS
    return bool(marker_hits and (has_diacritic or len(marker_hits) >= 2))


def _language_rejected(
    value: str,
    llm_result: dict,
    expected_concept: str,
) -> bool:
    if obvious_non_english_short_text(value):
        return True

    words = _tokens(value)
    if value.isascii() and len(words) <= 12:
        return False

    statistical = deterministic_english_check(value)
    if statistical is False:
        return True

    return llm_result.get("language", "") == "Non-English"


def _safe_normalized_value(raw_value: str, llm_result: dict) -> str:
    """Accept an LLM English correction only when it stays close to the input."""
    raw = normalize_whitespace(raw_value)
    candidate = normalize_whitespace(llm_result.get("normalized_value") or "")
    if not candidate:
        return raw

    raw_tokens = set(_tokens(raw))
    candidate_tokens = set(_tokens(candidate))
    if not raw_tokens or not candidate_tokens:
        return raw

    overlap = len(raw_tokens & candidate_tokens) / max(1, len(raw_tokens))
    if overlap < 0.50:
        return raw
    return candidate


def _contains_technical_solution_term(value: str) -> bool:
    lowered = value.casefold()
    if any(term in lowered for term in TECHNICAL_SOLUTION_WORDS):
        return True
    if any(term in lowered for term in SOLUTION_BIAS_TERMS):
        return True
    return False


def _validate_common(
    raw_value: str,
    allowed_concepts: Iterable[str],
    llm_result: dict,
    expected_concept: str | None = None,
) -> ValidationResult:
    value = normalize_whitespace(raw_value)
    allowed = set(allowed_concepts)
    expected = expected_concept or (next(iter(allowed)) if len(allowed) == 1 else "")

    if not value:
        return ValidationResult(False, reason="The answer cannot be empty.")

    if len(value) > 160:
        return ValidationResult(False, reason="Please give one short answer at a time.")

    adjusted = dict(llm_result)
    detected = adjusted.get("detected_concept", "")

    if detected not in allowed:
        return ValidationResult(
            False,
            detected_concept=detected,
            reason=(
                adjusted.get("reason")
                or "That answer does not fit what I am asking for."
            ),
            suggestion=adjusted.get("suggestion", ""),
        )

    guidance = CONCEPT_GUIDANCE[detected]
    if guidance["language_required"] and _language_rejected(value, adjusted, expected):
        return ValidationResult(
            False,
            detected_concept=detected,
            reason="Please answer in English only.",
            suggestion="",
        )

    if detected in {"OperationalCapability", "OperationalActivity"}:
        if _contains_technical_solution_term(value):
            return ValidationResult(
                False,
                detected_concept=detected,
                reason=(
                    "That sounds like a design or implementation detail. "
                    "Describe the operational need or action instead."
                ),
                suggestion="",
            )

    if adjusted.get("solution_bias", False):
        return ValidationResult(
            False,
            detected_concept=detected,
            reason=(
                adjusted.get("reason")
                or "That answer is too focused on a future solution. "
                "Describe what is needed operationally instead."
            ),
            suggestion=adjusted.get("suggestion", ""),
        )

    if not adjusted.get("valid", False):
        return ValidationResult(
            False,
            detected_concept=detected,
            reason=adjusted.get("reason") or "I cannot use that answer yet.",
            suggestion=adjusted.get("suggestion", ""),
        )

    normalized = _safe_normalized_value(value, adjusted)
    if not normalized:
        return ValidationResult(
            False,
            detected_concept=detected,
            reason="The answer became empty after validation.",
        )

    return ValidationResult(
        True,
        normalized_value=normalized,
        detected_concept=detected,
    )


def validate_llm_candidate(
    raw_value: str,
    expected_concept: str,
    llm_result: dict,
) -> ValidationResult:
    return _validate_common(
        raw_value,
        {expected_concept},
        llm_result,
        expected_concept=expected_concept,
    )


def _repair_human_role_contradiction(llm_result: dict) -> dict:
    """Repair a generic compact-model contradiction about professions/roles.

    If the model itself says that a candidate is a profession, occupation, job
    title, or human role but labels it Other, its explanation already establishes
    the ontology category: human roles are OperationalActors. No domain vocabulary
    or specific profession name is used here.
    """
    adjusted = dict(llm_result)
    if adjusted.get("detected_concept") != "Other":
        return adjusted
    if adjusted.get("solution_bias", False):
        return adjusted

    reason = str(adjusted.get("reason", "")).casefold()
    cues = (
        "profession",
        "occupation",
        "job title",
        "human role",
        "professional role",
    )
    if any(cue in reason for cue in cues):
        adjusted["detected_concept"] = "OperationalActor"
        adjusted["valid"] = True
        adjusted["reason"] = ""
        adjusted["suggestion"] = ""
    return adjusted


def validate_participant_candidate(
    raw_value: str,
    llm_result: dict,
) -> ValidationResult:
    value = normalize_whitespace(raw_value)

    if _contains_technical_solution_term(value):
        return ValidationResult(
            False,
            reason=(
                "That sounds like a technical system or solution. "
                "Here I need a real-world person, group, organization, resource, "
                "place, area, or environmental element."
            ),
        )

    if obvious_non_english_short_text(value):
        return ValidationResult(False, reason="Please answer in English only.")

    adjusted = _repair_human_role_contradiction(llm_result)
    detected = adjusted.get("detected_concept", "")

    if (
        detected in {"OperationalActor", "OperationalEntity"}
        and not adjusted.get("solution_bias", False)
    ):
        adjusted["valid"] = True
        if len(_tokens(value)) <= 12 and value.isascii():
            adjusted["language"] = "Language-neutral"

    result = _validate_common(
        raw_value,
        {"OperationalActor", "OperationalEntity"},
        adjusted,
    )
    if not result.accepted and detected == "Other":
        result.suggestion = ""
    return result
