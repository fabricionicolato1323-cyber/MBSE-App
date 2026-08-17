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
  facility, resource, place, area, environment, or contextual element.
- Other: an abstract quality, event, action, property, or phrase that should not
  become a participant/context candidate.

General rules:
- Extract each independently meaningful coordinated noun phrase separately.
- Preserve the exact wording used in the goal.
- Do not infer unstated stakeholders, systems, locations, or resources.
- Do not turn adjectives, qualities, goals, actions, or outcomes into participants.
- Do not favor any application domain.

Output JSON only.
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


def _clean_mention(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" ,;:.\t\n"))


def _classify_part(local_llm, part: str, context: str) -> str | None:
    """Classify one explicit noun phrase without any domain vocabulary.

    This uses the same semantic participant classifier used by the main workflow.
    No role names, asset names, industries, or scenario-specific nouns are embedded
    here. If the compact model is uncertain, no split is forced.
    """
    try:
        result = local_llm.validate_participant(part, context)
    except Exception:
        return None

    concept = str(result.get("detected_concept", "")).strip()
    valid = bool(result.get("valid", False))
    solution_bias = bool(result.get("solution_bias", False))

    if concept in CANDIDATE_TARGET_TYPES and valid and not solution_bias:
        return concept
    return None


def _split_coordinated_candidate(local_llm, raw: dict, goal: str) -> list[dict]:
    """Split a merged A-and-B candidate only after semantic classification.

    The split rule is domain-independent:
    1. both sides must occur literally in the user's goal;
    2. both sides must independently classify as a valid Actor or Entity;
    3. otherwise the original phrase is preserved.

    This prevents blind splitting of established compound phrases while still
    recovering when a small model merges two independently meaningful candidates.
    """
    mention = _clean_mention(str(raw.get("mention", "")))
    if not mention or " and " not in mention.casefold():
        return [raw]

    parts = [
        _clean_mention(part)
        for part in re.split(r"\band\b", mention, flags=re.IGNORECASE)
    ]
    if len(parts) != 2 or not all(parts):
        return [raw]
    if not all(_appears_in_text(part, goal) for part in parts):
        return [raw]

    concepts = [
        _classify_part(
            local_llm,
            part,
            context=(
                "This phrase was explicitly mentioned inside the operational goal. "
                "Classify only whether it is a real-world human participant or a "
                "non-human participant/context element."
            ),
        )
        for part in parts
    ]
    if any(concept is None for concept in concepts):
        return [raw]

    reason = _clean_mention(str(raw.get("reason", "")))
    return [
        {
            "mention": part,
            "candidate_concept": concept,
            "reason": reason or "Explicit real-world element mentioned in the goal.",
        }
        for part, concept in zip(parts, concepts)
    ]


def _expand_coordinated_candidates(local_llm, goal: str, candidates: Iterable[dict]) -> list[dict]:
    expanded: list[dict] = []
    for raw in candidates:
        expanded.extend(_split_coordinated_candidate(local_llm, raw, goal))
    return expanded


def filter_goal_candidates(
    goal: str,
    candidates: Iterable[dict],
    existing_names: Iterable[str] = (),
) -> list[dict]:
    """Deterministic write barrier for advisory LLM candidate extraction.

    A candidate must be an exact phrase from the goal, must map to an allowed
    participant/context concept, and must not duplicate an existing model element.
    The function contains no domain-specific participant or action vocabulary.
    """
    existing = {_canonical(name) for name in existing_names}
    seen: set[str] = set()
    accepted: list[dict] = []

    for raw in candidates:
        mention = _clean_mention(str(raw.get("mention", "")))
        concept = str(raw.get("candidate_concept", "")).strip()
        reason = _clean_mention(str(raw.get("reason", "")))
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
resources, places, areas, environments, or contextual elements that could be
useful candidates for the operational picture.

Do not infer missing stakeholders. Do not rewrite the wording. When the goal
contains two independently meaningful noun phrases joined by 'and', return them
as separate candidates when appropriate.
""".strip()

    result = local_llm._json_chat(
        [
            {"role": "system", "content": GOAL_CANDIDATE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        GOAL_CANDIDATE_SCHEMA,
    )

    raw_candidates = result.get("candidates", [])
    expanded = _expand_coordinated_candidates(local_llm, goal, raw_candidates)
    return filter_goal_candidates(
        goal,
        expanded,
        existing_names=existing_names,
    )
