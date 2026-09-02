from __future__ import annotations

from participant_rules import participant_nature_for_type
from validator import normalize_whitespace


class SimplifiedParticipantClassificationMixin:
    """Keep participant classification simple while protecting the OA boundary."""

    def _knowledge_boundary_assessment(self, value: str):
        knowledge = getattr(self, "knowledge", None)
        assess = getattr(knowledge, "assess_participant_phrase", None)
        if not callable(assess):
            return None
        return assess(value)

    def _participant_attributes(
        self,
        *,
        nature: str,
        reason: str,
        rules: list[str] | None = None,
        boundary_status: str = "confirmed_operational_participant",
        operational_roles: list[str] | None = None,
    ) -> dict:
        attributes = {
            "nature": nature,
            "classification_source": "user_choice",
            "classification_evidence": "user_confirmed",
            "classification_reason": reason,
            "classification_rules": list(rules or []),
            "boundary_status": boundary_status,
            "status": "confirmed",
            "confirmed_by": "user",
        }
        if operational_roles:
            attributes["operational_roles"] = list(operational_roles)
        return attributes

    def _reject_solution_candidate(self) -> None:
        add_notice = getattr(self, "add_notice", None)
        if callable(add_notice):
            add_notice(
                "This item was not added. The solution being designed is kept outside "
                "the operational model. Describe the people, organizations, existing "
                "systems, facilities, or environment involved in the operation instead."
            )

    def confirm_participant_classification(
        self,
        value: str,
        *,
        advisory_type: str | None = None,
        advisory_reason: str = "",
        advisory_source: str = "",
    ) -> tuple[str, str, dict] | None:
        """Resolve role realization / system boundary before the two OA choices.

        The Knowledge Graph supplies read-only semantic cues. The user still makes
        every fact decision, and only the final confirmed Actor/Entity classification
        is written to NetworkX.
        """
        del advisory_type, advisory_reason, advisory_source
        normalized = normalize_whitespace(value)
        assessment = self._knowledge_boundary_assessment(normalized)
        role_labels: list[str] = []
        kg_rules: list[str] = []

        if assessment is not None:
            rule_id = str(getattr(assessment, "rule_id", "") or "")
            if rule_id:
                kg_rules.append(rule_id)

            if assessment.kind == "role_realization":
                role_labels = [normalized]
                realization = self.ask_choice(
                    f"Who or what performs the '{normalized}' role in the current operational environment?",
                    [
                        ("human", "A person or human role"),
                        ("existing_technical", "An existing technical system or equipment"),
                        ("other_existing", "Another existing participant or organization"),
                        ("solution", "The solution being designed"),
                    ],
                    (
                        "A role name does not by itself prove whether the realizer is "
                        "human or technical."
                    ),
                )

                if realization == "human":
                    return (
                        "OperationalActor",
                        normalized,
                        self._participant_attributes(
                            nature="human_individual",
                            reason=(
                                "The Knowledge Graph detected a role-like label and the "
                                "user confirmed that it is realized by a person/human role."
                            ),
                            rules=kg_rules,
                            boundary_status="human_role_realizer",
                            operational_roles=role_labels,
                        ),
                    )

                if realization == "existing_technical":
                    return (
                        "OperationalEntity",
                        normalized,
                        self._participant_attributes(
                            nature="existing_technical_system",
                            reason=(
                                "The Knowledge Graph detected a role-like label and the "
                                "user confirmed an existing technical realizer."
                            ),
                            rules=kg_rules,
                            boundary_status="existing_technical_realizer",
                            operational_roles=role_labels,
                        ),
                    )

                if realization == "solution":
                    self._reject_solution_candidate()
                    return None

                # "other_existing" intentionally falls through to the normal
                # two-choice classification, while retaining the role semantics.

            elif assessment.kind in {"technical_boundary", "solution_boundary"}:
                boundary = self.ask_choice(
                    "How does this technical element relate to the solution you are defining?",
                    [
                        (
                            "existing",
                            "It already exists independently in the operational environment",
                        ),
                        ("solution", "It is the solution being designed"),
                        ("not_technical", "It is not a technical element"),
                    ],
                    (
                        "Existing external systems may belong in the operational model; "
                        "the solution being designed does not."
                    ),
                )
                if boundary == "existing":
                    return (
                        "OperationalEntity",
                        normalized,
                        self._participant_attributes(
                            nature="existing_technical_system",
                            reason=(
                                "The Knowledge Graph detected a technical/solution boundary "
                                "ambiguity and the user confirmed an existing technical participant."
                            ),
                            rules=kg_rules,
                            boundary_status="existing_technical_participant",
                        ),
                    )
                if boundary == "solution":
                    self._reject_solution_candidate()
                    return None
                # If the user says the phrase is not technical, continue with the
                # ordinary simplified classification rather than forcing a KG guess.

            elif assessment.kind == "existing_technical":
                existing = self.ask_choice(
                    "Does this name refer to an existing technical participant in the current operational environment?",
                    [
                        ("yes", "Yes, use it as an existing technical participant"),
                        ("different", "No, classify it differently"),
                    ],
                    "The Knowledge Graph found both technical and existing/external cues.",
                )
                if existing == "yes":
                    return (
                        "OperationalEntity",
                        normalized,
                        self._participant_attributes(
                            nature="existing_technical_system",
                            reason=(
                                "The Knowledge Graph detected explicit existing/external "
                                "technical wording and the user confirmed it."
                            ),
                            rules=kg_rules,
                            boundary_status="existing_technical_participant",
                        ),
                    )

        choice = self.ask_choice(
            "How should this participant be classified?",
            [
                (
                    "actor",
                    "Actor / role — person or human role (e.g., Driver, Operator)",
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
            self._participant_attributes(
                nature=nature,
                reason="Selected from the simplified two-option classification.",
                rules=kg_rules,
                operational_roles=role_labels,
            ),
        )
