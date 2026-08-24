from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


LEXICON_PATH = Path(__file__).with_name("participant_lexicon.json")

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


@lru_cache(maxsize=1)
def load_lexicon() -> dict[str, set[str]]:
    raw = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    return {
        key: {str(value).casefold() for value in values}
        for key, values in raw.items()
        if isinstance(values, list)
    }


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

    This is only a linguistic heuristic. It must not classify a participant by
    itself; it is used to catch a contradiction after semantic advice already
    identifies a human participant as an actor.
    """
    tokens = _tokens(value)
    if not tokens:
        return False

    plural_markers = {
        "both", "many", "multiple", "numerous", "several", "various",
        "people", "persons", "personnel", "children", "men", "women",
    }
    if set(tokens) & plural_markers:
        return True
    if any(token.isdigit() and int(token) > 1 for token in tokens):
        return True

    head = tokens[-1]
    singular_s_endings = (
        "analysis", "business", "corps", "news", "process", "series",
        "species", "status",
    )
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
    """Return transparent advice; never make the user's modeling decision."""
    lexicon = load_lexicon()
    heads = _head_forms(value)
    lowered = value.casefold()

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

    if heads & lexicon.get("collective_heads", set()):
        nature = (
            "population_or_community"
            if heads & {"community", "population"}
            else "team_or_collective"
        )
        return ParticipantSuggestion(
            "OperationalEntity",
            nature,
            "strong",
            "The head noun denotes a collective that may contain human actors.",
            ("COLLECTIVE_HEAD",),
        )

    if heads & lexicon.get("organization_heads", set()):
        nature = (
            "organizational_unit"
            if heads & {"department", "office"}
            else "organization"
        )
        return ParticipantSuggestion(
            "OperationalEntity",
            nature,
            "strong",
            "The head noun denotes an organization or organizational unit.",
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
        if any(marker in _tokens(lowered) for marker in existing):
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
