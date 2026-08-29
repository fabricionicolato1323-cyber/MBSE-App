from __future__ import annotations

import json

from app_base import CONFIG_PATH, KNOWLEDGE_BASE_DIR
from graph_model import OAGraph
from knowledge_graph import ArcadiaKnowledgeBase
from llm_service import OllamaLLM
from participant_rules import (
    ENTITY_NATURES,
    classify_participant,
    participant_nature_for_type,
)
from terminal_ui import processing_indicator
from validator import normalize_whitespace, validate_participant_candidate


_ENTITY_NATURE_LABELS = {
    "organization": "Organization",
    "organizational_unit": "Organizational unit",
    "team_or_collective": "Team or collective",
    "existing_technical_system": "External technical participant",
    "infrastructure_or_facility": "Infrastructure or facility",
    "external_operational_service": "External service",
    "population_or_community": "Population or community",
    "environmental_participant": "Environmental participant",
    "unspecified": "Other / not yet specified",
}


def _friendly_classification(concept: str | None, nature: str) -> str:
    if concept == "OperationalActor":
        return "Individual person or role"
    if concept == "OperationalEntity":
        return _ENTITY_NATURE_LABELS.get(nature, "Participant or context")
    return "No confident suggestion"


class UserExperienceMixin:
    """Translate internal model classifications into simpler user-facing language."""

    def __init__(self) -> None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.model = OAGraph()
        self.current_why = (
            "This helps build the operational picture one small step at a time."
        )
        self.notice = ""
        self.llm: OllamaLLM | None = None

        with processing_indicator("Loading model guidance"):
            self.knowledge = ArcadiaKnowledgeBase(KNOWLEDGE_BASE_DIR)

        ai_config = config.get("ollama", {})
        if ai_config.get("enabled", True):
            try:
                with processing_indicator("Connecting to AI assistance"):
                    self.llm = OllamaLLM(
                        base_url=ai_config.get(
                            "base_url",
                            "http://localhost:11434",
                        ),
                        model=ai_config.get("model") or None,
                        model_env=ai_config.get(
                            "model_env",
                            "MBSE_OLLAMA_MODEL",
                        ),
                        timeout_seconds=ai_config.get("timeout_seconds", 120),
                        keep_alive=ai_config.get("keep_alive"),
                        num_ctx=ai_config.get("num_ctx"),
                    )
                self.add_notice(
                    f"AI assistance connected. Selected model: {self.llm.model}"
                )
            except Exception:
                self.add_notice(
                    "AI assistance is unavailable. "
                    "The app will continue with deterministic rules."
                )

    def command(self, value: str) -> bool:
        raw = value.strip()
        cmd = raw.casefold()

        if cmd == "/ask":
            self.add_notice(
                "Add an English method question after the command.\n"
                "Format: /ask <method question>"
            )
            return True

        if cmd.startswith("/ask "):
            question = raw[5:].strip()
            if not question:
                self.add_notice("Please add a question after /ask.")
                return True

            if self.llm is not None:
                with self.ollama_operation(
                    "Querying model guidance with AI assistance"
                ) as ai_client:
                    answer = self.knowledge.answer(question, ai_client)
            else:
                with processing_indicator("Querying model guidance"):
                    answer = self.knowledge.answer(question, None)
            self.show_command_page("MODEL GUIDANCE ANSWER", answer)
            return True

        return super().command(value)

    def ask_entity_nature(self, suggested: str = "unspecified") -> str:
        ordered = [suggested] if suggested in ENTITY_NATURES else []
        ordered.extend(item for item in ENTITY_NATURES if item not in ordered)
        return self.ask_choice(
            "What kind of participant or context is it?",
            [(item, _ENTITY_NATURE_LABELS[item]) for item in ordered],
            "This helps distinguish different real-world participant and context types.",
        )

    def confirm_participant_classification(
        self,
        value: str,
        *,
        advisory_type: str | None = None,
        advisory_reason: str = "",
        advisory_source: str = "",
    ) -> tuple[str, str, dict] | None:
        normalized = normalize_whitespace(value)
        suggestion = classify_participant(normalized)

        concept = suggestion.concept
        nature = suggestion.nature
        reason = suggestion.reason
        source = "deterministic_rules"
        evidence = suggestion.evidence_level
        rule_ids = list(suggestion.rule_ids)

        if (
            not suggestion.actionable
            and not suggestion.solution_bias
            and suggestion.evidence_level in {"insufficient", "ambiguous"}
            and advisory_type in {"OperationalActor", "OperationalEntity"}
        ):
            concept = advisory_type
            nature = participant_nature_for_type(normalized, advisory_type)
            reason = advisory_reason or "AI-assisted classification suggestion."
            source = advisory_source or "ai_advisory"
            evidence = "advisory"
            rule_ids = []

        while True:
            self.current_why = reason or (
                "The classification determines which structural rules apply "
                "while keeping the final decision with you."
            )

            details = [
                f"  Candidate: {normalized}",
                f"  Suggested: {_friendly_classification(concept, nature)}",
                "  The suggestion is advisory; you make the final choice.",
            ]
            choices: list[tuple[str, str]] = []
            if concept in {"OperationalActor", "OperationalEntity"}:
                choices.append(("confirm", "Confirm the suggestion"))
            choices.extend(
                [
                    ("actor", "Treat as an individual person or role"),
                    (
                        "entity",
                        "Treat as a group, organization, resource, place, or context",
                    ),
                ]
            )
            if self.llm is not None:
                choices.append(("ai", "Ask AI for another opinion"))
            choices.append(("reject", "Do not add this participant or context"))

            choice = self.ask_choice(
                "How should this participant or context be treated?",
                choices,
                "Only your explicit choice is written to the model.",
                extra_lines=details,
            )

            if choice == "ai":
                try:
                    with self.ollama_operation(
                        "Requesting another AI opinion"
                    ) as llm:
                        result = validate_participant_candidate(
                            normalized,
                            llm.validate_participant(normalized),
                        )
                except Exception:
                    self.add_notice("AI advice was unavailable.")
                    continue

                if not result.accepted:
                    self.add_notice(
                        "AI did not produce a usable participant classification."
                    )
                    continue

                concept = result.detected_concept
                nature = participant_nature_for_type(normalized, concept)
                reason = result.reason or "AI-assisted classification suggestion."
                source = "ai_advisory"
                evidence = "advisory"
                rule_ids = []
                continue

            if choice == "reject":
                return None

            if choice == "actor":
                concept = "OperationalActor"
                nature = "human_individual"
                source = "user_override"
                evidence = "user_confirmed"
                reason = "User selected an individual person or role."
                rule_ids = []
            elif choice == "entity":
                concept = "OperationalEntity"
                nature = self.ask_entity_nature(nature)
                source = "user_override"
                evidence = "user_confirmed"
                reason = "User selected a participant or context classification."
                rule_ids = []
            elif choice == "confirm" and concept == "OperationalEntity":
                if nature == "unspecified":
                    nature = self.ask_entity_nature(nature)

            attributes = {
                "nature": nature,
                "classification_source": source,
                "classification_evidence": evidence,
                "classification_reason": reason,
                "classification_rules": rule_ids,
                "status": "confirmed",
                "confirmed_by": "user",
            }
            return str(concept), normalized, attributes
