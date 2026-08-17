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
- CandidateMention is a TRANSIENT helper concept used only by the assistant.
- A CandidateMention is an exact noun phrase found in user wording (for example,
  a goal). It is never written to the NetworkX model by itself.
- The user must explicitly confirm the candidate before it can become an
  OperationalActor or OperationalEntity.
- Example: "Keep infrastructure and soldiers safe" may yield the transient
  candidates "infrastructure" -> OperationalEntity and "soldiers" ->
  OperationalActor. The words are only candidates until the user confirms them.
"""

NODE_TYPES = {
    "OperationalCapability",
    "OperationalActor",
    "OperationalEntity",
    "OperationalActivity",
}

PARTICIPANT_TYPES = {"OperationalActor", "OperationalEntity"}

# These helper concepts belong to the guided elicitation layer, not to the
# persistent Arcadia OA graph.
TRANSIENT_HELPER_CONCEPTS = {"CandidateMention"}
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
        "example": "Keep restricted airspace safe",
        "language_required": True,
    },
    "OperationalActor": {
        "definition": "A human operational participant or human role.",
        "friendly_name": "human participant",
        "expected_format": "One human role or person name.",
        "example": "Air Traffic Controller",
        "language_required": False,
    },
    "OperationalEntity": {
        "definition": (
            "A non-human real-world participant or contextual element involved in the "
            "operation, such as an organization, group, facility, building, area, "
            "environment, location, infrastructure, resource, or external party. An "
            "Operational Entity may contain other Operational Entities or Operational Actors."
        ),
        "friendly_name": "non-human participant or context",
        "expected_format": "One real-world participant, place, area, resource, or context name.",
        "example": "Airport Operations Center",
        "language_required": False,
    },
    "OperationalActivity": {
        "definition": (
            "An operational action performed by a participant. It describes what happens "
            "in the operation, not software, hardware, architecture, or implementation."
        ),
        "friendly_name": "action",
        "expected_format": "One short English action phrase, preferably starting with a verb.",
        "example": "Assess incoming threat information",
        "language_required": True,
    },
    "OperationalExchange": {
        "definition": (
            "Information, material, request, or another operational item exchanged between "
            "two operational actions."
        ),
        "friendly_name": "interaction",
        "expected_format": "One short English noun phrase naming what is exchanged.",
        "example": "Threat assessment",
        "language_required": True,
    },
    "CommunicationMean": {
        "definition": (
            "A real-world operational communication method used by two participants to "
            "support an interaction. Keep it solution-independent where possible."
        ),
        "friendly_name": "communication method",
        "expected_format": "One short English phrase naming the communication method.",
        "example": "Voice communication",
        "language_required": True,
    },
}

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
