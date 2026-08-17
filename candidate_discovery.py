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


def _canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _appears_in_text(mention: str, text: str) -> bool:
    return _canonical(mention) in _canonical(text)


def filter_goal_candidates(
    goal: str,
    candidates: Iterable[dict],
    existing_names: Iterable[str] = (),
) -> list[dict]:
    """Deterministic barrier for LLM candidate extraction.

    Candidate discovery is advisory only. A candidate must be an exact phrase from
    the goal, must map to an allowed OA participant/context concept, and must not
    duplicate something that is already in the model.
    """
    existing = {_canonical(name) for name in existing_names}
    seen: set[str] = set()
    accepted: list[dict] = []

    for raw in candidates:
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


def extract_goal_candidates(local_llm, goal: str, existing_names: Iterable[str] = ()) -> list[dict]:
    prompt = f"""
Operational goal:
{goal}

Extract only explicit real-world people, human groups, organizations, facilities,
infrastructure, places, areas, environments, resources, or contextual elements
that could be useful candidates for the operational picture.

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
