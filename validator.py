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

from ontology import CONCEPT_GUIDANCE
from participant_rules import classify_participant, looks_like_plural_participant_label
from semantic_policy import policy_terms


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


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-zà-ÿ]+", value.casefold())


def _token_set(value: str) -> set[str]:
    return set(_tokens(value))


def obvious_non_english_short_text(value: str) -> bool:
    """Use only externally configured high-confidence language markers."""
    tokens = _token_set(value)
    if not tokens:
        return False
    has_diacritic = bool(re.search(r"[^\x00-\x7F]", value))
    marker_hits = tokens & policy_terms("non_english_markers")
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


def contains_high_confidence_solution_bias(value: str) -> bool:
    """Return True only for configured, explicit implementation wording."""
    lowered = value.casefold()
    return any(
        term in lowered
        for term in policy_terms("technical_solution_terms")
    )


def reconcile_activity_frame_solution_bias(
    raw_value: str,
    frame_result: dict,
) -> dict:
    """Keep compact-model solution-bias guesses advisory when rules disagree.

    Ollama is used to decompose complex activity sentences, not as the final
    write authority. If it returns usable clauses but labels ordinary behavior
    as implementation bias without any explicit configured technical marker,
    retain the warning for the user and allow the normal deterministic clause
    validation and confirmation flow to continue.
    """
    adjusted = dict(frame_result)
    if not adjusted.get("solution_bias", False):
        return adjusted
    if contains_high_confidence_solution_bias(raw_value):
        return adjusted
    if not adjusted.get("valid", False) or not adjusted.get("clauses"):
        return adjusted

    adjusted["solution_bias"] = False
    adjusted["advisory_warning"] = (
        normalize_whitespace(str(adjusted.get("reason") or ""))
        or "Ollama flagged possible implementation bias."
    )
    adjusted["reason"] = ""
    adjusted["solution_bias_source"] = "deterministic_override"
    return adjusted


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
        if contains_high_confidence_solution_bias(value):
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
    """Repair a compact-model contradiction using configurable semantic cues."""
    adjusted = dict(llm_result)
    if adjusted.get("detected_concept") != "Other":
        return adjusted
    if adjusted.get("solution_bias", False):
        return adjusted

    reason = str(adjusted.get("reason", "")).casefold()
    if any(cue in reason for cue in policy_terms("human_role_reason_cues")):
        adjusted["detected_concept"] = "OperationalActor"
        adjusted["valid"] = True
        adjusted["reason"] = ""
        adjusted["suggestion"] = ""
    return adjusted


def _repair_plural_actor_contradiction(value: str, llm_result: dict) -> dict:
    """Keep plural human role-holders out of the indivisible Actor category."""
    adjusted = dict(llm_result)
    if (
        adjusted.get("detected_concept") == "OperationalActor"
        and not adjusted.get("solution_bias", False)
        and looks_like_plural_participant_label(value)
    ):
        adjusted["detected_concept"] = "OperationalEntity"
        adjusted["valid"] = True
        adjusted["reason"] = (
            "The phrase denotes multiple human role-holders; in this application, "
            "a human collective is an Operational Entity."
        )
    return adjusted


def validate_participant_candidate(
    raw_value: str,
    llm_result: dict,
) -> ValidationResult:
    value = normalize_whitespace(raw_value)

    rule_advice = classify_participant(value)
    if rule_advice.solution_bias:
        return ValidationResult(
            False,
            reason=(
                "That wording appears to describe a proposed solution. "
                "An existing external technical participant may be valid, but the "
                "future System of Interest must not be introduced in OA."
            ),
        )

    if obvious_non_english_short_text(value):
        return ValidationResult(False, reason="Please answer in English only.")

    adjusted = _repair_human_role_contradiction(llm_result)
    original_detected = adjusted.get("detected_concept", "")
    adjusted = _repair_plural_actor_contradiction(value, adjusted)
    plural_repaired = (
        original_detected == "OperationalActor"
        and adjusted.get("detected_concept") == "OperationalEntity"
    )
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
    if result.accepted and plural_repaired:
        result.reason = str(adjusted.get("reason", ""))
    if not result.accepted and detected == "Other":
        result.suggestion = ""
    return result
