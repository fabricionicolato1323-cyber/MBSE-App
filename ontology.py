"""Restricted Arcadia Operational Analysis ontology for the guided prototype.

Arcadia terminology is intentionally internal. The user-facing application talks
about goals, participants, actions, interactions, and communication methods.
"""

NODE_TYPES = {
    "OperationalCapability",
    "OperationalActor",
    "OperationalEntity",
    "OperationalActivity",
}

PARTICIPANT_TYPES = {"OperationalActor", "OperationalEntity"}

ALLOWED_RELATIONS = {
    ("OperationalActor", "PERFORMS", "OperationalActivity"),
    ("OperationalEntity", "PERFORMS", "OperationalActivity"),
    ("OperationalActivity", "SUPPORTS_CAPABILITY", "OperationalCapability"),
    ("OperationalActivity", "OPERATIONAL_EXCHANGE", "OperationalActivity"),
    ("OperationalActor", "COMMUNICATION_MEAN", "OperationalActor"),
    ("OperationalActor", "COMMUNICATION_MEAN", "OperationalEntity"),
    ("OperationalEntity", "COMMUNICATION_MEAN", "OperationalActor"),
    ("OperationalEntity", "COMMUNICATION_MEAN", "OperationalEntity"),
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
            "A non-human real-world participant or stakeholder involved in the operation, "
            "such as an organization, group, facility, environment, or external party."
        ),
        "friendly_name": "non-human participant",
        "expected_format": "One real-world participant name.",
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

# High-confidence implementation terms used only as a deterministic safety net.
# Semantic solution-bias detection is still performed by the LLM.
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
