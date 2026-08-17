from __future__ import annotations

import re
from typing import Iterable

from ontology import CANDIDATE_TARGET_TYPES


GOAL_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "mention": {"type": "string"},
                    "candidate_concept": {
                        "type": "string",
                        "enum": ["OperationalActor", "OperationalEntity", "Other"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["mention", "candidate_concept", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


GOAL_CANDIDATE_SYSTEM = """
You help a guided Operational Analysis assistant discover possible real-world
participants and contextual elements that are explicitly mentioned in a goal.

Do not invent anything. Extract only noun phrases that occur literally in the
user's goal. A candidate is only a possible model element; the user will confirm
it before anything is added to the model.

Classify each extracted mention as one of:
- OperationalActor: a person, human role, or human group.
- OperationalEntity: a non-human real-world stakeholder, organization, group,
  facility, infrastructure, place, area, environment, resource, or context element.
- Other: an abstract quality, event, action, or word that should not become a
  participant/context candidate.

Important examples:
Goal: "Keep infrastructure and soldiers safe"
Candidates:
- "infrastructure" -> OperationalEntity
- "soldiers" -> OperationalActor
Do not return "infrastructure and soldiers" as one combined candidate.
Do not extract "safe".

Goal: "Maintain safe airspace operations"
Candidate:
- "airspace" -> OperationalEntity
Do not extract "safe" or "operations" merely because they are nouns.

Goal: "Protect civilians from flooding"
Candidate:
- "civilians" -> OperationalActor
Do not extract "flooding" as a participant.

Preserve the exact wording used in the goal. Output JSON only.
""".strip()


_EXCLUDED_MENTIONS = {
    "safe",
    "safety",
    "secure",
    "security",
    "goal",
    "outcome",
    "capability",
    "mission",
    "operation",
    "operations",
}

# These vocabularies are deliberately small and high-confidence. They are not a
# general NLP classifier; they only provide a deterministic fallback when a small
# local model merges clearly different coordinated mentions into one phrase.
_HUMAN_HINTS = {
    "person", "people", "civilian", "civilians", "soldier", "soldiers",
    "pilot", "pilots", "operator", "operators", "controller", "controllers",
    "officer", "officers", "worker", "workers", "guard", "guards",
    "responder", "responders", "staff", "personnel", "crew", "commander",
    "commanders", "technician", "technicians", "driver", "drivers",
}

_ENTITY_HINTS = {
    "infrastructure", "facility", "facilities", "building", "buildings",
    "base", "bases", "station", "stations", "site", "sites", "area", "areas",
    "zone", "zones", "airspace", "region", "regions", "airport", "airports",
    "center", "centers", "centre", "centres", "organization", "organizations",
    "organisation", "organisations", "authority", "authorities", "department",
    "departments", "service", "services", "unit", "units", "team", "teams",
    "environment", "environments", "warehouse", "warehouses", "port", "ports",
    "terminal", "terminals", "road", "roads", "bridge", "bridges",
}


def _canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z]+", value.casefold())


def _appears_in_text(mention: str, text: str) -> bool:
    return _canonical(mention) in _canonical(text)


def _concept_hint(mention: str) -> str | None:
    tokens = set(_tokens(mention))
    if tokens & _HUMAN_HINTS:
        return "OperationalActor"
    if tokens & _ENTITY_HINTS:
        return "OperationalEntity"
    return None


def _split_coordinated_candidate(raw: dict, goal: str) -> list[dict]:
    """Split a merged candidate only when each side has a confident OA hint.

    Example:
      "infrastructure and soldiers" ->
          "infrastructure" (OperationalEntity)
          "soldiers" (OperationalActor)

    We intentionally do not split phrases such as "command and control center"
    because both sides do not independently have a confident candidate meaning.
    """
    mention = re.sub(r"\s+", " ", str(raw.get("mention", "")).strip())
    if " and " not in mention.casefold():
        return [raw]

    parts = [part.strip(" ,") for part in re.split(r"\band\b", mention, flags=re.IGNORECASE)]
    if len(parts) != 2 or not all(parts):
        return [raw]

    concepts = [_concept_hint(part) for part in parts]
    if any(concept is None for concept in concepts):
        return [raw]
    if not all(_appears_in_text(part, goal) for part in parts):
        return [raw]

    reason = re.sub(r"\s+", " ", str(raw.get("reason", "")).strip())
    return [
        {
            "mention": part,
            "candidate_concept": concept,
            "reason": reason or "Explicit real-world element mentioned in the goal.",
        }
        for part, concept in zip(parts, concepts)
    ]


def _expand_coordinated_candidates(goal: str, candidates: Iterable[dict]) -> list[dict]:
    expanded: list[dict] = []
    for raw in candidates:
        expanded.extend(_split_coordinated_candidate(raw, goal))
    return expanded


def filter_goal_candidates(
    goal: str,
    candidates: Iterable[dict],
    existing_names: Iterable[str] = (),
) -> list[dict]:
    """Deterministic barrier for LLM candidate extraction.

    Candidate discovery is advisory only. A candidate must be an exact phrase from
    the goal, must map to an allowed OA participant/context concept, and must not
    duplicate something that is already in the model.

    Before filtering, high-confidence coordinated phrases are split into separate
    candidates. This makes the workflow robust when a compact LLM returns
    "infrastructure and soldiers" as one candidate instead of two.
    """
    existing = {_canonical(name) for name in existing_names}
    seen: set[str] = set()
    accepted: list[dict] = []

    for raw in _expand_coordinated_candidates(goal, candidates):
        mention = re.sub(r"\s+", " ", str(raw.get("mention", "")).strip())
        concept = str(raw.get("candidate_concept", "")).strip()
        reason = re.sub(r"\s+", " ", str(raw.get("reason", "")).strip())
        canonical = _canonical(mention)

        if not mention or len(mention) > 80:
            continue
        if concept not in CANDIDATE_TARGET_TYPES:
            continue
        if canonical in _EXCLUDED_MENTIONS:
            continue
        if canonical in existing or canonical in seen:
            continue
        if not _appears_in_text(mention, goal):
            continue

        accepted.append(
            {
                "mention": mention,
                "candidate_concept": concept,
                "reason": reason,
            }
        )
        seen.add(canonical)

    return accepted


def extract_goal_candidates(
    local_llm,
    goal: str,
    existing_names: Iterable[str] = (),
) -> list[dict]:
    prompt = f"""
Operational goal:
{goal}

Extract only explicit real-world people, human groups, organizations, facilities,
infrastructure, places, areas, environments, resources, or contextual elements
that could be useful candidates for the operational picture.

When the goal contains separate coordinated objects, return them as separate
candidates. Example: "infrastructure and soldiers" must be returned as two
candidates, not one combined phrase.

Do not infer missing stakeholders. Do not rewrite or singularize the wording.
""".strip()

    result = local_llm._json_chat(
        [
            {"role": "system", "content": GOAL_CANDIDATE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        GOAL_CANDIDATE_SCHEMA,
    )
    return filter_goal_candidates(
        goal,
        result.get("candidates", []),
        existing_names=existing_names,
    )
