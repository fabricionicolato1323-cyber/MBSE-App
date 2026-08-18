from __future__ import annotations

import re

from ontology import SOLUTION_BIAS_TERMS


# Grammatical constructors commonly used to express desired outcomes/states.
# This is deliberately domain-neutral: no scenario, asset, profession, or mission
# vocabulary belongs here.
OUTCOME_CONSTRUCTION_VERBS = {
    "achieve",
    "allow",
    "avoid",
    "enable",
    "ensure",
    "improve",
    "keep",
    "maintain",
    "maximize",
    "minimize",
    "preserve",
    "prevent",
    "protect",
    "reduce",
    "safeguard",
    "secure",
    "support",
    "sustain",
}

TECHNICAL_IMPLEMENTATION_TERMS = {
    "system",
    "software",
    "application",
    "platform",
    "algorithm",
    "database",
    "microservice",
    "api",
    "source code",
    "python script",
    "software module",
    "cloud architecture",
}

# High-confidence function words/verbs used only to avoid fast-accepting a short
# non-English phrase. This is language vocabulary, not operational-domain data.
NON_ENGLISH_FAST_MARKERS = {
    # Portuguese
    "de", "da", "do", "das", "dos", "para", "com", "sem", "que", "manter",
    "proteger", "reduzir", "garantir", "melhorar", "seguro", "segura",
    # German
    "der", "die", "das", "und", "oder", "mit", "ohne", "für", "halten",
    "schützen", "reduzieren", "sicherstellen",
    # Spanish / French
    "el", "la", "los", "las", "con", "sin", "mantener", "proteger",
    "le", "les", "avec", "sans", "maintenir", "protéger",
}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z]+", value.casefold())


def _contains_implementation_term(value: str) -> bool:
    lowered = value.casefold()
    return any(term in lowered for term in TECHNICAL_IMPLEMENTATION_TERMS) or any(
        term in lowered for term in SOLUTION_BIAS_TERMS
    )


def fast_operational_goal_result(value: str) -> dict | None:
    """Return a validation-shaped result for a clearly formed operational goal.

    The fast path intentionally handles only high-confidence, short outcome/state
    constructions. Ambiguous wording falls through to the LLM. It never decides
    from scenario-specific nouns.
    """
    normalized = _normalize(value)
    if not normalized or len(normalized) > 160 or not normalized.isascii():
        return None

    tokens = _tokens(normalized)
    if not 3 <= len(tokens) <= 18:
        return None

    first_index = 1 if tokens[0] == "to" and len(tokens) > 1 else 0
    if tokens[first_index] not in OUTCOME_CONSTRUCTION_VERBS:
        return None

    if _contains_implementation_term(normalized):
        return None

    marker_hits = set(tokens) & NON_ENGLISH_FAST_MARKERS
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
