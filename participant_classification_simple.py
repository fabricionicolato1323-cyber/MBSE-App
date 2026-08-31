from __future__ import annotations

from participant_rules import participant_nature_for_type
from validator import normalize_whitespace


class SimplifiedParticipantClassificationMixin:
    """Reduce participant classification to the two persisted OA concepts."""

    def confirm_participant_classification(
        self,
        value: str,
        *,
        advisory_type: str | None = None,
        advisory_reason: str = "",
        advisory_source: str = "",
    ) -> tuple[str, str, dict]:
        """Ask only Actor / role versus Entity / context.

        The presentation deliberately avoids exposing the internal Arcadia concept
        names. The selected option is still persisted as OperationalActor or
        OperationalEntity so the model and downstream SysML translation remain
        unchanged.
        """
        del advisory_type, advisory_reason, advisory_source
        normalized = normalize_whitespace(value)
        choice = self.ask_choice(
            "How should this participant be classified?",
            [
                (
                    "actor",
                    "Actor / role — person or role (e.g., Driver, Operator)",
                ),
                (
                    "entity",
                    "Entity / context — group, organization, system or place (e.g., Train, Station)",
                ),
            ],
            "Choose the one classification that best describes this operational participant.",
        )

        if choice == "actor":
            concept = "OperationalActor"
            nature = "human_individual"
        else:
            concept = "OperationalEntity"
            nature = participant_nature_for_type(normalized, concept)

        return (
            concept,
            normalized,
            {
                "nature": nature,
                "classification_source": "user_choice",
                "classification_evidence": "user_confirmed",
                "classification_reason": "Selected from the simplified two-option classification.",
                "classification_rules": [],
                "status": "confirmed",
                "confirmed_by": "user",
            },
        )
