from __future__ import annotations

import re
from typing import Iterable


SEMANTIC_FRAME_SCHEMA = {
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "language": {
            "type": "string",
            "enum": ["English", "Non-English", "Language-neutral"],
        },
        "solution_bias": {"type": "boolean"},
        "reason": {"type": "string"},
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subjects": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "verb": {"type": "string"},
                    "objects": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "recipients": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "time": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "other_complements": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "activity_text": {"type": "string"},
                },
                "required": [
                    "subjects",
                    "verb",
                    "objects",
                    "recipients",
                    "locations",
                    "conditions",
                    "time",
                    "other_complements",
                    "activity_text",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["valid", "language", "solution_bias", "reason", "clauses"],
    "additionalProperties": False,
}


SEMANTIC_FRAME_SYSTEM = """
You are a domain-neutral semantic frame parser for an Operational Analysis
assistant. Parse one user answer describing operational behavior. Do not modify
any graph and do not invent facts.

Return one clause for each independently meaningful operational action.
Each clause has:
- subjects: who or what performs the action;
- verb: the main action verb only;
- objects: things directly acted on, observed, changed, handled, or produced;
- recipients: explicit destinations/receivers of information, material, requests,
  commands, services, or other transferred items;
- locations: explicit places/areas where the action occurs;
- conditions: explicit conditions such as if/when/unless clauses;
- time: explicit timing, sequence, duration, or frequency expressions;
- other_complements: meaningful complements that do not fit the fields above;
- activity_text: a concise verb phrase for the action, without an explicit subject.

General parsing rules:
1. Be domain-independent. Never require a known list of professions, assets,
   industries, or action verbs.
2. Do not invent subjects, objects, recipients, places, conditions, or timing.
3. If the user omits the subject, use the supplied default subject.
4. If a coordinated sentence states the subject once and then gives several
   actions, inherit that subject for the following clauses.
5. One verb with several coordinated objects is ONE clause. Example pattern:
   "Monitor A and B" -> one clause, verb="Monitor", objects=["A", "B"].
6. Several independent verbs are SEPARATE clauses. Example pattern:
   "Monitor A and report B" -> two clauses.
7. Several coordinated subjects performing the same verb remain ONE clause with
   multiple subjects.
8. Preserve explicit complements. Do not turn every noun into an object when it
   actually functions as a recipient, location, condition, or time expression.
9. activity_text must preserve the user's meaning and should be suitable as the
   name of one operational activity.
10. Mark valid=false for text that does not actually describe operational
    behavior. Mark solution_bias=true for premature implementation/design content.
11. Natural-language content must be English. Proper names can be language-neutral.
12. Output JSON only using the supplied schema.
""".strip()


_COMPLEXITY_MARKERS = re.compile(
    r"(?:[,;]|\b(?:and|or|then|while|when|before|after|if|unless|until|because|during)\b)",
    flags=re.IGNORECASE,
)


def looks_structurally_complex(value: str) -> bool:
    """Cheap, domain-neutral hint used only for UI/confirmation behavior."""
    text = re.sub(r"\s+", " ", value.strip())
    return bool(_COMPLEXITY_MARKERS.search(text))


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _clean_list(values: object, limit: int = 12) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in values[:limit]:
        value = _clean(raw)
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def normalize_semantic_frames(
    raw_result: dict,
    *,
    default_subject: str,
    max_clauses: int = 8,
) -> dict:
    """Normalize LLM frame output and safely propagate omitted subjects."""
    result = {
        "valid": bool(raw_result.get("valid", False)),
        "language": _clean(raw_result.get("language")) or "English",
        "solution_bias": bool(raw_result.get("solution_bias", False)),
        "reason": _clean(raw_result.get("reason")),
        "clauses": [],
    }

    raw_clauses = raw_result.get("clauses", [])
    if not isinstance(raw_clauses, list):
        result["valid"] = False
        result["reason"] = (
            result["reason"]
            or "I could not identify a usable action structure."
        )
        return result

    inherited_subjects = [default_subject] if default_subject else []

    for raw_clause in raw_clauses[:max_clauses]:
        if not isinstance(raw_clause, dict):
            continue

        subjects = _clean_list(raw_clause.get("subjects"))
        if not subjects:
            subjects = list(inherited_subjects)
        else:
            inherited_subjects = list(subjects)

        verb = _clean(raw_clause.get("verb"))
        activity_text = _clean(raw_clause.get("activity_text"))
        if not verb or not activity_text:
            continue

        clause = {
            "subjects": subjects,
            "verb": verb,
            "objects": _clean_list(raw_clause.get("objects")),
            "recipients": _clean_list(raw_clause.get("recipients")),
            "locations": _clean_list(raw_clause.get("locations")),
            "conditions": _clean_list(raw_clause.get("conditions")),
            "time": _clean_list(raw_clause.get("time")),
            "other_complements": _clean_list(
                raw_clause.get("other_complements")
            ),
            "activity_text": activity_text,
        }
        result["clauses"].append(clause)

    if result["valid"] and not result["clauses"]:
        result["valid"] = False
        result["reason"] = (
            result["reason"]
            or "I could not identify a usable action structure."
        )

    return result


def parse_activity_frames(
    local_llm,
    text: str,
    *,
    default_subject: str,
    known_subjects: Iterable[str] = (),
    context: str = "",
) -> dict:
    known = [name for name in known_subjects if _clean(name)]
    prompt = f"""
Current participant / default subject: {default_subject or 'Not specified'}
Known participants in the model: {', '.join(known) if known else 'None'}
Current model context: {context or 'No additional context.'}
User answer: {text}

Parse the answer into semantic action clauses. If the answer omits its subject,
use the current participant as the subject. If it explicitly names several
subjects, preserve all of them. Distinguish multiple objects of one action from
multiple independent verbs/actions. Preserve recipients, locations, conditions,
and time expressions separately.
""".strip()

    raw = local_llm._json_chat(
        [
            {"role": "system", "content": SEMANTIC_FRAME_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        SEMANTIC_FRAME_SCHEMA,
        max_tokens=760,
    )
    result = normalize_semantic_frames(
        raw,
        default_subject=default_subject,
    )

    # Compact models sometimes mislabel a very short ASCII action phrase as
    # Non-English. Do not make that single label authoritative; the normal
    # deterministic language/write barrier still validates each activity_text.
    words = re.findall(r"[A-Za-z]+", text)
    if (
        result.get("language") == "Non-English"
        and text.isascii()
        and len(words) <= 5
    ):
        result["language"] = "Language-neutral"

    return result


def frame_is_complex(frame_result: dict) -> bool:
    clauses = frame_result.get("clauses", [])
    if len(clauses) != 1:
        return True
    if not clauses:
        return False
    clause = clauses[0]
    return any(
        len(clause.get(field, [])) > 1
        for field in (
            "subjects",
            "objects",
            "recipients",
            "locations",
            "conditions",
            "time",
        )
    ) or any(
        clause.get(field)
        for field in (
            "recipients",
            "locations",
            "conditions",
            "time",
            "other_complements",
        )
    )


def format_frame_summary(frame_result: dict) -> str:
    clauses = frame_result.get("clauses", [])
    lines = ["I understood the following action structure:"]
    for index, clause in enumerate(clauses, start=1):
        lines.append(
            f"  {index}. Action: {clause.get('activity_text', '')}"
        )
        lines.append(
            "     Subject(s): "
            + (
                ", ".join(clause.get("subjects", []))
                or "(not identified)"
            )
        )
        lines.append(f"     Verb: {clause.get('verb', '')}")
        if clause.get("objects"):
            lines.append(
                "     Object(s): " + ", ".join(clause["objects"])
            )
        if clause.get("recipients"):
            lines.append(
                "     Recipient(s): "
                + ", ".join(clause["recipients"])
            )
        if clause.get("locations"):
            lines.append(
                "     Location(s): "
                + ", ".join(clause["locations"])
            )
        if clause.get("conditions"):
            lines.append(
                "     Condition(s): "
                + ", ".join(clause["conditions"])
            )
        if clause.get("time"):
            lines.append("     Time: " + ", ".join(clause["time"]))
        if clause.get("other_complements"):
            lines.append(
                "     Other complement(s): "
                + ", ".join(clause["other_complements"])
            )
    return "\n".join(lines)
