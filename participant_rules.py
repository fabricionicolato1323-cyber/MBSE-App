from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from semantic_policy import policy_terms


DEFAULT_LEXICON_PATH = Path(__file__).with_name("participant_lexicon.json")
DEFAULT_EXTENSION_PATH = Path(__file__).with_name("participant_lexicon_extensions.json")
LEXICON_ENV = "MBSE_PARTICIPANT_LEXICON_PATH"
LEXICON_EXTENSION_ENV = "MBSE_PARTICIPANT_LEXICON_EXTENSIONS_PATH"

ENTITY_NATURES = (
    "organization",
    "organizational_unit",
    "team_or_collective",
    "existing_technical_system",
    "infrastructure_or_facility",
    "external_operational_service",
    "population_or_community",
    "environmental_participant",
    "unspecified",
)


@dataclass(frozen=True)
class ParticipantSuggestion:
    concept: str | None
    nature: str
    evidence_level: str
    reason: str
    rule_ids: tuple[str, ...]
    solution_bias: bool = False

    @property
    def actionable(self) -> bool:
        return self.concept in {"OperationalActor", "OperationalEntity"}


def _load_lexicon_file(path: Path) -> dict[str, set[str]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        key: {str(value).casefold() for value in values}
        for key, values in raw.items()
        if isinstance(values, list)
    }


@lru_cache(maxsize=1)
def load_lexicon() -> dict[str, set[str]]:
    """Load replaceable base vocabulary plus optional local extensions.

    The classifier algorithm stays in Python, but no scenario vocabulary is
    embedded in it. Both the base semantic vocabulary and any local/domain
    extension can be replaced without code changes.
    """
    configured_base = os.getenv(LEXICON_ENV, "").strip()
    base_path = (
        Path(configured_base).expanduser()
        if configured_base
        else DEFAULT_LEXICON_PATH
    )
    merged = _load_lexicon_file(base_path)

    configured_extension = os.getenv(LEXICON_EXTENSION_ENV, "").strip()
    extension_path = (
        Path(configured_extension).expanduser()
        if configured_extension
        else DEFAULT_EXTENSION_PATH
    )
    extensions = _load_lexicon_file(extension_path)
    for key, values in extensions.items():
        merged.setdefault(key, set()).update(values)
    return merged


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", value.casefold())


def _head_forms(value: str) -> set[str]:
    tokens = _tokens(value)
    if not tokens:
        return set()
    head = tokens[-1]
    forms = {head}
    if head.endswith("ies") and len(head) > 3:
        forms.add(head[:-3] + "y")
    elif head.endswith("s") and not head.endswith("ss") and len(head) > 3:
        forms.add(head[:-1])
    return forms


def _contains_phrase(value: str, phrases: set[str]) -> bool:
    normalized = re.sub(r"\s+", " ", value.casefold()).strip()
    return any(phrase in normalized for phrase in phrases)


def looks_like_plural_participant_label(value: str) -> bool:
    """Return a conservative English surface-form signal for plurality.

    The vocabulary for this linguistic heuristic is external configuration. The
    signal cannot classify a participant by itself; it only repairs a semantic
    contradiction after a human participant was already identified as an actor.
    """
    tokens = _tokens(value)
    if not tokens:
        return False

    if set(tokens) & policy_terms("plural_markers"):
        return True
    if any(token.isdigit() and int(token) > 1 for token in tokens):
        return True

    head = tokens[-1]
    singular_s_endings = policy_terms("singular_s_endings")
    return (
        len(head) > 3
        and head.endswith("s")
        and not head.endswith(("ss", "us", "is"))
        and head not in singular_s_endings
    )


def participant_nature_for_type(value: str, concept: str) -> str:
    """Suggest app-specific nature metadata for an already selected OA type."""
    suggestion = classify_participant(value)
    if suggestion.concept == concept:
        return suggestion.nature
    if concept == "OperationalActor":
        return "human_individual"
    if concept == "OperationalEntity" and looks_like_plural_participant_label(value):
        return "team_or_collective"
    return "unspecified"


def classify_participant(value: str) -> ParticipantSuggestion:
    """Return transparent deterministic advice; never persist a user fact."""
    lexicon = load_lexicon()
    heads = _head_forms(value)

    if not heads:
        return ParticipantSuggestion(
            None,
            "unspecified",
            "insufficient",
            "No usable noun phrase was found.",
            ("EMPTY_OR_INVALID",),
        )

    if _contains_phrase(value, lexicon.get("solution_markers", set())):
        return ParticipantSuggestion(
            None,
            "unspecified",
            "strong",
            "The wording appears to name a proposed solution, not an OA participant.",
            ("PROPOSED_SOLUTION_MARKER",),
            solution_bias=True,
        )

    if heads & lexicon.get("communication_heads", set()):
        return ParticipantSuggestion(
            None,
            "unspecified",
            "strong",
            "The head noun normally denotes a communication mean, not a participant.",
            ("COMMUNICATION_HEAD",),
        )

    if heads & lexicon.get("information_heads", set()):
        return ParticipantSuggestion(
            None,
            "unspecified",
            "strong",
            "The head noun normally denotes exchanged information, not a participant.",
            ("INFORMATION_HEAD",),
        )

    if heads & lexicon.get("actor_heads", set()):
        return ParticipantSuggestion(
            "OperationalActor",
            "human_individual",
            "strong",
            "The head noun denotes an indivisible human role or person.",
            ("HUMAN_ROLE_HEAD",),
        )

    if heads & lexicon.get("population_heads", set()):
        return ParticipantSuggestion(
            "OperationalEntity",
            "population_or_community",
            "strong",
            "The head noun denotes a population or community.",
            ("POPULATION_HEAD",),
        )

    if heads & lexicon.get("collective_heads", set()):
        return ParticipantSuggestion(
            "OperationalEntity",
            "team_or_collective",
            "strong",
            "The head noun denotes a collective that may contain human actors.",
            ("COLLECTIVE_HEAD",),
        )

    if heads & lexicon.get("organizational_unit_heads", set()):
        return ParticipantSuggestion(
            "OperationalEntity",
            "organizational_unit",
            "strong",
            "The head noun denotes an organizational unit.",
            ("ORGANIZATIONAL_UNIT_HEAD",),
        )

    if heads & lexicon.get("organization_heads", set()):
        return ParticipantSuggestion(
            "OperationalEntity",
            "organization",
            "strong",
            "The head noun denotes an organization.",
            ("ORGANIZATION_HEAD",),
        )

    if heads & lexicon.get("facility_heads", set()):
        return ParticipantSuggestion(
            "OperationalEntity",
            "infrastructure_or_facility",
            "partial",
            "The phrase denotes a facility; confirm that it participates operationally.",
            ("FACILITY_HEAD",),
        )

    if heads & lexicon.get("technical_heads", set()):
        existing = lexicon.get("existing_markers", set())
        if any(marker in _tokens(value) for marker in existing):
            return ParticipantSuggestion(
                "OperationalEntity",
                "existing_technical_system",
                "partial",
                "The wording identifies an existing or external technical participant.",
                ("EXISTING_TECHNICAL_HEAD",),
            )
        return ParticipantSuggestion(
            None,
            "existing_technical_system",
            "ambiguous",
            "A technical element may be an existing participant or premature solution bias.",
            ("AMBIGUOUS_TECHNICAL_HEAD",),
        )

    if heads & lexicon.get("environment_heads", set()):
        return ParticipantSuggestion(
            "OperationalEntity",
            "environmental_participant",
            "partial",
            "The phrase denotes operational environment; confirm that modeling it adds value.",
            ("ENVIRONMENT_HEAD",),
        )

    return ParticipantSuggestion(
        None,
        "unspecified",
        "insufficient",
        "The deterministic rules do not have enough evidence to classify this phrase.",
        ("NO_MATCHING_RULE",),
    )
