"""Persistent ontology for the reduced Arcadia Operational Analysis builder.

The application persists exactly six OA concepts. Definitions, examples,
input contracts, and relationship signatures live here so the guided flow and
the graph write barrier use the same source of truth.
"""

from __future__ import annotations

import re


NODE_TYPES = {
    "OperationalCapability",
    "OperationalActor",
    "OperationalEntity",
    "OperationalActivity",
    "OperationalExchange",
    "CommunicationMean",
}

PARTICIPANT_TYPES = {"OperationalActor", "OperationalEntity"}

CONCEPT_GUIDANCE = {
    "OperationalCapability": {
        "friendly_name": "operational capability",
        "definition": (
            "A solution-independent ability or operational outcome required "
            "by stakeholders in the operational context."
        ),
        "example": "Maintain secure access to the restricted area",
        "expected_format": (
            "verb + desired state or object + optional operational condition"
        ),
        "capella_type": "OperationalCapability",
        "composition_relation": "REFINES_INTO",
    },
    "OperationalActor": {
        "friendly_name": "operational actor",
        "definition": (
            "A non-decomposable Operational Entity that participates directly "
            "in the operation and is usually a human person or role."
        ),
        "example": "Field Coordinator",
        "expected_format": "concise noun phrase naming one non-decomposable participant",
        "capella_type": "OperationalActor",
        "composition_relation": None,
    },
    "OperationalEntity": {
        "friendly_name": "operational entity",
        "definition": (
            "A real-world organization, group, place, resource, context, or "
            "existing external participant involved in the operation."
        ),
        "example": "Field Patrol Team",
        "expected_format": (
            "noun phrase naming a real-world group, organization, place, "
            "resource, context, or external participant"
        ),
        "capella_type": "OperationalEntity",
        "composition_relation": "CONTAINS",
    },
    "OperationalActivity": {
        "friendly_name": "operational activity",
        "definition": (
            "Operational behavior performed by an actor or entity, expressed "
            "without implementation or system-design detail."
        ),
        "example": "Verify access authorization",
        "expected_format": "action verb + object + optional complements",
        "capella_type": "OperationalActivity",
        "composition_relation": "DECOMPOSES_INTO",
    },
    "OperationalExchange": {
        "friendly_name": "operational exchange",
        "definition": (
            "Identifiable information, request, command, event, or material "
            "transferred from one operational activity to another."
        ),
        "example": "Access authorization data",
        "expected_format": "noun phrase naming the exchanged content or item",
        "capella_type": "OperationalInteraction",
        "composition_relation": "REFINES_INTO",
    },
    "CommunicationMean": {
        "friendly_name": "communication mean",
        "definition": (
            "A real operational method or support connecting participants and "
            "enabling one or more operational exchanges."
        ),
        "example": "Voice radio communication",
        "expected_format": (
            "noun phrase naming the real operational communication method"
        ),
        "capella_type": "CommunicationMean",
        "composition_relation": "REFINES_INTO",
    },
}


RELATION_GUIDANCE = {
    "PERFORMS": {
        "definition": "A participant carries out an operational activity.",
        "example": "Field Patrol Team performs Verify access authorization",
    },
    "INVOLVED_IN_CAPABILITY": {
        "definition": "A participant contributes to an operational capability.",
        "example": "Field Patrol Team is involved in Maintain secure access",
    },
    "SUPPORTS_CAPABILITY": {
        "definition": "An activity contributes to achieving a capability.",
        "example": "Verify access authorization supports Maintain secure access",
    },
    "SOURCE_ACTIVITY": {
        "definition": "The activity that produces an operational exchange.",
        "example": "Access authorization data has source Verify identity",
    },
    "TARGET_ACTIVITY": {
        "definition": "The activity that consumes an operational exchange.",
        "example": "Access authorization data has target Permit entry",
    },
    "SOURCE_PARTICIPANT": {
        "definition": "The originating endpoint of a communication mean.",
        "example": "Voice radio communication has source Field Patrol Team",
    },
    "TARGET_PARTICIPANT": {
        "definition": "The receiving endpoint of a communication mean.",
        "example": "Voice radio communication has target Operations Center",
    },
    "SUPPORTS_EXCHANGE": {
        "definition": "A communication mean enables an operational exchange.",
        "example": "Voice radio communication supports Incident notification",
    },
    "CONTAINS": {
        "definition": (
            "An Operational Entity structurally contains another entity or actor."
        ),
        "example": "Security Organization contains Field Patrol Team",
    },
    "LOCATED_IN": {
        "definition": (
            "A participant operates within a physical or operational place or context."
        ),
        "example": "Field Patrol Team is located in Restricted Area",
    },
    "DECOMPOSES_INTO": {
        "definition": "An activity is broken down into subordinate activities.",
        "example": "Protect area decomposes into Monitor access points",
    },
    "REFINES_INTO": {
        "definition": (
            "A capability, exchange, or communication mean is made more "
            "operationally specific without implying structural ownership."
        ),
        "example": "Maintain security refines into Prevent unauthorized access",
    },
}


ALLOWED_RELATIONS = {
    ("OperationalActor", "PERFORMS", "OperationalActivity"),
    ("OperationalEntity", "PERFORMS", "OperationalActivity"),
    ("OperationalActor", "INVOLVED_IN_CAPABILITY", "OperationalCapability"),
    ("OperationalEntity", "INVOLVED_IN_CAPABILITY", "OperationalCapability"),
    ("OperationalActivity", "SUPPORTS_CAPABILITY", "OperationalCapability"),
    ("OperationalExchange", "SOURCE_ACTIVITY", "OperationalActivity"),
    ("OperationalExchange", "TARGET_ACTIVITY", "OperationalActivity"),
    ("CommunicationMean", "SOURCE_PARTICIPANT", "OperationalActor"),
    ("CommunicationMean", "SOURCE_PARTICIPANT", "OperationalEntity"),
    ("CommunicationMean", "TARGET_PARTICIPANT", "OperationalActor"),
    ("CommunicationMean", "TARGET_PARTICIPANT", "OperationalEntity"),
    ("CommunicationMean", "SUPPORTS_EXCHANGE", "OperationalExchange"),
    ("OperationalEntity", "CONTAINS", "OperationalEntity"),
    ("OperationalEntity", "CONTAINS", "OperationalActor"),
    ("OperationalActor", "LOCATED_IN", "OperationalEntity"),
    ("OperationalEntity", "LOCATED_IN", "OperationalEntity"),
    ("OperationalActivity", "DECOMPOSES_INTO", "OperationalActivity"),
    ("OperationalCapability", "REFINES_INTO", "OperationalCapability"),
    ("OperationalExchange", "REFINES_INTO", "OperationalExchange"),
    ("CommunicationMean", "REFINES_INTO", "CommunicationMean"),
}


COMPOSITION_RELATIONS = {"CONTAINS", "DECOMPOSES_INTO", "REFINES_INTO"}
ENDPOINT_RELATIONS = {
    "SOURCE_ACTIVITY",
    "TARGET_ACTIVITY",
    "SOURCE_PARTICIPANT",
    "TARGET_PARTICIPANT",
}
CONSTRAINT_OPERATORS = {"MIN", "MAX", "EQUAL", "RANGE"}
CONSTRAINT_SCOPES = {"LOCAL", "HIERARCHY"}
AGGREGATION_RULES = {"SUM", "MIN", "MAX", "ALL", "ANY", "CUSTOM"}


_VERB_ENDINGS = ("ate", "fy", "ise", "ize")
_COMMON_OPERATIONAL_VERBS = {
    "accept", "achieve", "acquire", "activate", "allocate", "allow", "approve",
    "assess", "assign", "assist", "authorize", "avoid", "capture", "check",
    "collect", "communicate", "complete", "confirm", "contain", "control",
    "coordinate", "create", "decide", "deliver", "detect", "determine",
    "dispatch", "distribute", "enable", "ensure", "establish", "evaluate",
    "execute", "facilitate", "gather", "handle", "identify", "inform",
    "inspect", "keep", "locate", "maintain", "manage", "measure", "mitigate",
    "monitor", "notify", "observe", "operate", "organize", "permit", "plan",
    "prepare", "prevent", "process", "protect", "provide", "receive", "record",
    "recover", "reduce", "release", "report", "request", "respond", "restore",
    "review", "route", "schedule", "secure", "select", "send", "share",
    "supply", "support", "sustain", "track", "transfer", "transport", "validate",
    "verify", "warn",
}

_IMPLEMENTATION_TERMS = {
    "api", "class", "code", "container", "database", "docker", "kubernetes",
    "microservice", "python", "schema", "script", "software module",
}


def concept_guidance(concept: str) -> dict:
    return CONCEPT_GUIDANCE[concept]


def relation_guidance(relation: str) -> dict:
    return RELATION_GUIDANCE[relation]


def _words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]*", value)


def validate_concept_name(concept: str, value: str) -> tuple[bool, str]:
    """Apply a small, transparent grammar contract without semantic guessing."""
    words = _words(value.strip())
    if not words:
        return False, "Enter a non-empty English phrase."
    if len(value.strip()) < 3:
        return False, "The phrase is too short to identify the concept clearly."

    first = words[0].casefold()
    lowered = value.casefold()
    if any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in _IMPLEMENTATION_TERMS):
        return False, (
            "Describe the operational need or behavior without implementation "
            "technology or software-design detail."
        )
    if concept in {"OperationalCapability", "OperationalActivity"}:
        looks_like_verb = (
            first in _COMMON_OPERATIONAL_VERBS
            or first.endswith(_VERB_ENDINGS)
        )
        if not looks_like_verb:
            return False, "Start the phrase with an operational action verb."
        if len(words) < 2:
            return False, "Add the desired state, object, or operational outcome."
    elif concept == "OperationalActor":
        if len(words) > 8:
            return False, "Use one concise noun phrase for one non-decomposable participant."
    elif concept in {"OperationalExchange", "CommunicationMean"}:
        if first in _COMMON_OPERATIONAL_VERBS:
            return False, "Use a noun phrase, not an action phrase."

    return True, ""


def ontology_catalog() -> dict:
    """Serializable ontology catalog stored with every saved model."""
    return {
        "concepts": CONCEPT_GUIDANCE,
        "relationships": RELATION_GUIDANCE,
        "allowed_relations": [list(item) for item in sorted(ALLOWED_RELATIONS)],
    }
