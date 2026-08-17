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


# Short inputs are extremely unreliable for statistical language detectors.
# We only use langdetect when there is enough text to make the result useful.
def deterministic_english_check(value: str) -> Optional[bool]:
    words = re.findall(r"[A-Za-zÀ-ÿ]+", value)
    letters = sum(len(word) for word in words)
    if len(words) < 6 or letters < 35:
        return None
    if not _HAS_LANGDETECT or detect is None:
        return None
    try:
        return detect(value) == "en"
    except LangDetectException:
        return None


HUMAN_ROLE_WORDS = {
    "controller", "operator", "pilot", "officer", "dispatcher", "coordinator",
    "technician", "analyst", "manager", "inspector", "supervisor", "driver",
}

ENTITY_LABEL_WORDS = {
    "control", "authority", "agency", "department", "team", "center", "centre",
    "organization", "organisation", "unit", "service", "facility", "airport",
    "company", "office", "command", "administration", "operations",
}

TECHNICAL_SOLUTION_WORDS = {
    "system", "software", "application", "platform", "algorithm", "database",
    "microservice", "sensor network", "api",
}

# High-confidence English action verbs. This is not a grammar checker; it is only
# a deterministic signal that a short phrase is action-like. Third-person forms
# are accepted too, because users often answer "provides ..." or "detects ...".
ACTION_VERBS = {
    "assess", "assesses", "authorize", "authorizes", "check", "checks",
    "communicate", "communicates", "control", "controls", "coordinate", "coordinates",
    "detect", "detects", "determine", "determines", "evaluate", "evaluates",
    "identify", "identifies", "inform", "informs", "inspect", "inspects",
    "maintain", "maintains", "manage", "manages", "monitor", "monitors",
    "notify", "notifies", "observe", "observes", "provide", "provides",
    "receive", "receives", "report", "reports", "request", "requests",
    "respond", "responds", "send", "sends", "share", "shares", "track", "tracks",
    "transfer", "transfers", "update", "updates", "verify", "verifies", "warn", "warns",
    "protect", "protects", "supervise", "supervises", "support", "supports",
    "plan", "plans", "prioritize", "prioritizes", "classify", "classifies",
}

# Very common non-English markers used only as a high-confidence short-input guard.
# The LLM remains the primary language classifier; this list prevents us from
# accepting obvious Portuguese/German/Spanish/French answers when the phrase is short.
NON_ENGLISH_MARKERS = {
    # Portuguese
    "o", "a", "os", "as", "de", "da", "do", "das", "dos", "para", "com", "sem",
    "e", "ou", "que", "como", "avaliar", "detectar", "fornecer", "informar", "controlar",
    "ameaça", "ameaças", "informação", "informações", "posição", "velocidade",
    # German
    "der", "die", "das", "den", "dem", "des", "und", "oder", "mit", "ohne", "für",
    "über", "erkennen", "melden", "bereitstellen", "steuern", "überwachen",
    # Spanish/French common action markers
    "el", "la", "los", "las", "y", "con", "sin", "detectar", "proporcionar",
    "le", "les", "et", "avec", "sans", "détecter", "fournir",
}


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-zà-ÿ]+", value.casefold())


def _token_set(value: str) -> set[str]:
    return set(_tokens(value))


def participant_type_hint(value: str) -> str | None:
    """Conservative deterministic hint for short participant labels."""
    lowered = normalize_whitespace(value).casefold()
    tokens = _token_set(lowered)

    if any(term in lowered for term in TECHNICAL_SOLUTION_WORDS):
        return None
    if tokens & HUMAN_ROLE_WORDS:
        return "OperationalActor"
    if tokens & ENTITY_LABEL_WORDS:
        return "OperationalEntity"
    return None


def starts_with_action_verb(value: str) -> bool:
    tokens = _tokens(value)
    return bool(tokens and tokens[0] in ACTION_VERBS)


def obvious_non_english_short_text(value: str) -> bool:
    """Return True only for high-confidence non-English short phrases.

    We deliberately bias toward not rejecting ambiguous short English inputs.
    """
    tokens = _token_set(value)
    if not tokens:
        return False
    # Accented letters are a useful signal, but names should not be rejected here.
    has_diacritic = bool(re.search(r"[^\x00-\x7F]", value))
    marker_hits = tokens & NON_ENGLISH_MARKERS
    return bool(marker_hits and (has_diacritic or len(marker_hits) >= 2))


def _language_rejected(value: str, llm_result: dict, expected_concept: str) -> bool:
    """Combine LLM and deterministic language checks conservatively.

    For short action phrases, an English leading verb overrides a bad small-model
    language classification. This fixes cases such as "informs drone informations".
    """
    if obvious_non_english_short_text(value):
        return True

    statistical = deterministic_english_check(value)
    if statistical is False:
        return True

    llm_language = llm_result.get("language", "")
    if llm_language != "Non-English":
        return False

    if expected_concept == "OperationalActivity" and starts_with_action_verb(value):
        return False

    # Short ASCII labels/phrases are too uncertain to reject solely on one small
    # model classification unless there is a deterministic non-English signal.
    words = _tokens(value)
    if len(words) <= 5 and value.isascii():
        return False

    return True


def _safe_normalized_value(raw_value: str, llm_result: dict) -> str:
    """Use LLM normalization only when it remains recognizably close to the input."""
    raw = normalize_whitespace(raw_value)
    candidate = normalize_whitespace(llm_result.get("normalized_value") or "")
    if not candidate:
        return raw

    raw_tokens = set(_tokens(raw))
    candidate_tokens = set(_tokens(candidate))
    if not raw_tokens or not candidate_tokens:
        return raw

    overlap = len(raw_tokens & candidate_tokens) / max(1, len(raw_tokens))
    # Prevent the local model from replacing the user's fact with an invented example.
    if overlap < 0.50:
        return raw
    return candidate


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

    # Deterministic structural override for actions. If the user starts with a
    # clear action verb, do not let the small model misclassify "Provide X" as an
    # exchange merely because X is information.
    adjusted = dict(llm_result)
    if expected == "OperationalActivity" and starts_with_action_verb(value):
        adjusted["detected_concept"] = "OperationalActivity"
        adjusted["valid"] = True
        adjusted["reason"] = ""
        adjusted["suggestion"] = ""

    detected = adjusted.get("detected_concept", "")
    if detected not in allowed:
        return ValidationResult(
            False,
            detected_concept=detected,
            reason=adjusted.get("reason") or "That answer does not fit what I am asking for.",
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

    lowered = value.lower()
    if detected in {"OperationalCapability", "OperationalActivity"}:
        matched = next((term for term in SOLUTION_BIAS_TERMS if term in lowered), None)
        if matched:
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
                or "That answer is too focused on a future solution. Describe what is needed operationally instead."
            ),
            suggestion=adjusted.get("suggestion", ""),
        )

    # For action phrases, the deterministic action-form check is authoritative.
    # We intentionally do not reject broad actions as "too vague". Refinement can
    # happen later; the write barrier protects type and solution-domain constraints.
    if expected == "OperationalActivity" and starts_with_action_verb(value):
        return ValidationResult(
            True,
            normalized_value=_safe_normalized_value(value, adjusted),
            detected_concept="OperationalActivity",
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
        return ValidationResult(False, detected_concept=detected, reason="The answer became empty after validation.")

    return ValidationResult(True, normalized_value=normalized, detected_concept=detected)


def validate_llm_candidate(raw_value: str, expected_concept: str, llm_result: dict) -> ValidationResult:
    return _validate_common(raw_value, {expected_concept}, llm_result, expected_concept=expected_concept)


def validate_participant_candidate(raw_value: str, llm_result: dict) -> ValidationResult:
    value = normalize_whitespace(raw_value)
    lowered = value.casefold()

    if any(term in lowered for term in TECHNICAL_SOLUTION_WORDS):
        return ValidationResult(
            False,
            reason=(
                "That sounds like a technical system or solution. Here I need a real-world "
                "party in the operation, such as a person, team, organization, authority, or facility."
            ),
        )

    adjusted = dict(llm_result)
    hint = participant_type_hint(raw_value)

    # Only reject the language when there is a high-confidence signal. Short
    # stakeholder labels are often misclassified by compact local models.
    if obvious_non_english_short_text(value):
        return ValidationResult(False, reason="Please answer in English only.")

    if adjusted.get("solution_bias", False):
        return _validate_common(raw_value, {"OperationalActor", "OperationalEntity"}, adjusted)

    if hint:
        adjusted["detected_concept"] = hint
        adjusted["valid"] = True
        adjusted["normalized_value"] = adjusted.get("normalized_value") or value
        adjusted["reason"] = ""
        adjusted["suggestion"] = ""
    elif adjusted.get("detected_concept") in {"OperationalActor", "OperationalEntity"}:
        adjusted["valid"] = True
        # A short ASCII participant label should not fail only because the model
        # called its language Non-English.
        if len(_tokens(value)) <= 5 and value.isascii():
            adjusted["language"] = "Language-neutral"

    result = _validate_common(raw_value, {"OperationalActor", "OperationalEntity"}, adjusted)
    if not result.accepted and adjusted.get("detected_concept") == "Other":
        result.suggestion = ""
    return result
