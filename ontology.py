"""Restricted Arcadia Operational Analysis ontology for the guided prototype.

Arcadia terminology is intentionally internal. The user-facing application talks
about goals, participants, actions, interactions, structure, places, and
communication methods.

Structural convention:
- CONTAINS is stored from the larger Operational Entity to the contained
  Operational Entity or Operational Actor.
- PART_OF is the inverse meaning of CONTAINS and is not stored as a second edge.
- LOCATED_IN is separate from structural containment so organizational
  decomposition is not confused with physical/operational location.

Guided-elicitation convention:
- CandidateMention is a transient helper concept used only by the assistant.
- SemanticFrame and SemanticClause are transient parsing concepts used to
  decompose natural-language activity answers into subjects, verbs, objects,
  recipients, locations, conditions, time, and other complements.
- Transient helper concepts are never written as Arcadia nodes in NetworkX.
- The user must confirm candidate participants and complex activity
  decompositions before the corresponding OA elements are persisted.
- Candidate discovery and semantic parsing are domain-independent and must never
  depend on scenario-specific names, roles, assets, industries, or actions.
"""

NODE_TYPES = {
    "OperationalCapability",
    "OperationalActor",
    "OperationalEntity",
    "OperationalActivity",
}

PARTICIPANT_TYPES = {"OperationalActor", "OperationalEntity"}

# Participant type, participant nature, and operational role are deliberately
# separate dimensions. Roles are attributes because the same participant may
# play different roles in different capabilities or scenarios.
PARTICIPANT_NATURES = {
    "human_individual",
    "organization",
    "organizational_unit",
    "team_or_collective",
    "existing_technical_system",
    "infrastructure_or_facility",
    "external_operational_service",
    "population_or_community",
    "environmental_participant",
    "unspecified",
}

OPERATIONAL_ROLES = {
    "initiator",
    "requester",
    "performer",
    "operator",
    "coordinator",
    "decision_authority",
    "information_provider",
    "information_consumer",
    "service_provider",
    "regulator",
    "support_or_maintainer",
    "responder",
    "beneficiary",
    "affected_party",
    "observer",
    "adversary",
}

# Helper concepts belong to the elicitation/parsing layer, not the persistent OA graph.
TRANSIENT_HELPER_CONCEPTS = {
    "CandidateMention",
    "SemanticFrame",
    "SemanticClause",
}
CANDIDATE_TARGET_TYPES = {"OperationalActor", "OperationalEntity"}

ALLOWED_RELATIONS = {
    ("OperationalActor", "PERFORMS", "OperationalActivity"),
    ("OperationalEntity", "PERFORMS", "OperationalActivity"),
    ("OperationalActivity", "SUPPORTS_CAPABILITY", "OperationalCapability"),
    ("OperationalActivity", "OPERATIONAL_EXCHANGE", "OperationalActivity"),
    ("OperationalActor", "COMMUNICATION_MEAN", "OperationalActor"),
    ("OperationalActor", "COMMUNICATION_MEAN", "OperationalEntity"),
    ("OperationalEntity", "COMMUNICATION_MEAN", "OperationalActor"),
    ("OperationalEntity", "COMMUNICATION_MEAN", "OperationalEntity"),

    # Explicit same-type decomposition. Entity/participant composition continues
    # to use CONTAINS so structural membership remains represented only once.
    ("OperationalCapability", "DECOMPOSES", "OperationalCapability"),
    ("OperationalActivity", "DECOMPOSES", "OperationalActivity"),

    # Structural decomposition. Operational Actors are leaves: they may be
    # contained by an Operational Entity but do not contain other participants.
    ("OperationalEntity", "CONTAINS", "OperationalEntity"),
    ("OperationalEntity", "CONTAINS", "OperationalActor"),

    # Operational / physical location. This is deliberately distinct from
    # CONTAINS/PART_OF.
    ("OperationalActor", "LOCATED_IN", "OperationalEntity"),
    ("OperationalEntity", "LOCATED_IN", "OperationalEntity"),
}

CONCEPT_GUIDANCE = {
    "OperationalCapability": {
        "definition": (
            "An operational outcome or ability needed by stakeholders. It must describe "
            "the desired operational result, not the system or solution to be built."
        ),
        "friendly_name": "goal",
        "expected_format": "One short English outcome phrase.",
        "example": "Maintain safe and effective operations",
        "language_required": True,
    },
    "OperationalActor": {
        "definition": (
            "One indivisible human operational participant or human role. "
            "A collective of humans is modeled as an Operational Entity."
        ),
        "friendly_name": "human participant",
        "expected_format": "One human role or person name.",
        "example": "Operations Coordinator",
        "language_required": False,
    },
    "OperationalEntity": {
        "definition": (
            "A collective or non-human real-world participant/context involved in the "
            "operation, such as an organization, team, existing external technical "
            "participant, facility, service, population, community, or environmental "
            "participant. It may contain Operational Entities or Operational Actors."
        ),
        "friendly_name": "collective or non-human participant/context",
        "expected_format": "One collective or real-world participant/context name.",
        "example": "Operations Facility",
        "language_required": False,
    },
    "OperationalActivity": {
        "definition": (
            "An operational action performed by one or more participants. It describes "
            "what happens in the operation, not software, hardware, architecture, or "
            "implementation. One natural-language answer may be decomposed into several "
            "Operational Activities when it contains several independent actions."
        ),
        "friendly_name": "action",
        "expected_format": (
            "One English action phrase or a natural sentence containing one or more "
            "subjects, actions, objects, and complements."
        ),
        "example": "Coordinate service requests and report status",
        "language_required": True,
    },
    "OperationalExchange": {
        "definition": (
            "Information, material, request, or another operational item exchanged between "
            "two operational actions."
        ),
        "friendly_name": "interaction",
        "expected_format": "One short English noun phrase naming what is exchanged.",
        "example": "Status information",
        "language_required": True,
    },
    "CommunicationMean": {
        "definition": (
            "A real-world operational communication method used by two participants to "
            "support an interaction. Keep it solution-independent where possible."
        ),
        "friendly_name": "communication method",
        "expected_format": "One short English phrase naming the communication method.",
        "example": "Direct communication",
        "language_required": True,
    },
}

# High-confidence implementation terms used only as a deterministic safety net.
# They are technology categories, not scenario-specific examples.
SOLUTION_BIAS_TERMS = {
    "microservice",
    "database schema",
    "rest api",
    "python script",
    "c++ class",
    "software module",
    "cloud architecture",
    "kubernetes",
    "docker container",
    "implementation class",
    "source code",
    "software architecture",
}
