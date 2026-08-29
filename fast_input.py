from __future__ import annotations

import re

from semantic_policy import policy_terms


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z]+", value.casefold())


def _contains_implementation_term(value: str) -> bool:
    lowered = value.casefold()
    return any(
        term in lowered
        for term in policy_terms("technical_solution_terms")
    )


def fast_operational_goal_result(value: str) -> dict | None:
    """Return a validation-shaped result for a clearly formed operational goal.

    The fast path handles only high-confidence, short outcome/state constructions.
    Its vocabulary is loaded from the external semantic policy; Python contains
    only the algorithm. Ambiguous wording falls through to the AI validator.
    """
    normalized = _normalize(value)
    if not normalized or len(normalized) > 160 or not normalized.isascii():
        return None

    tokens = _tokens(normalized)
    if not 3 <= len(tokens) <= 18:
        return None

    first_index = 1 if tokens[0] == "to" and len(tokens) > 1 else 0
    if tokens[first_index] not in policy_terms("goal_outcome_verbs"):
        return None

    if _contains_implementation_term(normalized):
        return None

    marker_hits = set(tokens) & policy_terms("non_english_markers")
    if len(marker_hits) >= 2:
        return None

    return {
        "valid": True,
        "language": "English",
        "detected_concept": "OperationalCapability",
        "normalized_value": normalized,
        "solution_bias": False,
        "reason": "",
        "suggestion": "",
        "validation_source": "fast_rule",
    }
