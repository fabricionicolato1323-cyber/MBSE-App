from __future__ import annotations


class CapabilityStructuralFlowMixin:
    """Use the Knowledge Graph to inspect capability text before persistence.

    The KG supplies structural vocabulary, policy, and optional lexical knowledge.
    This mixin only orchestrates user confirmation and the existing write barrier.
    The local LLM is never asked to identify predicates, mentions, or model facts.
    """

    def _analyze_capability(self, value: str):
        analyze = getattr(getattr(self, "knowledge", None), "analyze_capability_statement", None)
        return analyze(value) if callable(analyze) else None

    def _confirmed_capability_texts(self, value: str) -> list[str] | None:
        analysis = self._analyze_capability(value)
        if analysis is None:
            return [value]

        if analysis.requires_simplification:
            self.add_notice(
                "This statement contains more structural complexity than the configured "
                "deterministic analyzer can resolve confidently. Please express one main "
                "goal at a time. Nothing was added to the model."
            )
            return None

        candidates = list(analysis.capability_candidates)
        if len(candidates) <= 1:
            return [value]

        lines = [
            "The Knowledge Graph found multiple independently stated goal candidates:"
        ]
        lines.extend(
            f"  {index}. {candidate}"
            for index, candidate in enumerate(candidates, start=1)
        )
        self.add_notice("\n".join(lines))

        if self.ask_yes_no(
            "Should these be treated as separate goals?",
            (
                "Independent predicates may represent distinct operational outcomes. "
                "Nothing is separated unless you confirm it."
            ),
        ):
            return candidates
        return [value]

    def capture_goals(self) -> list[tuple[str, str]]:
        goals: list[tuple[str, str]] = []
        first = True

        while first or self.ask_yes_no(
            "Is there another important goal?",
            "Some operations have more than one important outcome. Add another only if it is genuinely distinct.",
        ):
            while True:
                source_text = self.ask_validated(
                    question="What is the main goal?" if first else "What is the other goal?",
                    explanation="Describe the desired operational outcome, not a system or implementation.",
                    expected_concept="OperationalCapability",
                    why=(
                        "The goal gives the rest of the model a clear purpose and helps "
                        "prevent premature solution design."
                    ),
                )
                confirmed = self._confirmed_capability_texts(source_text)
                if confirmed is not None:
                    break

            analysis = self._analyze_capability(source_text)
            for goal_text in confirmed:
                goal_id = self.add_node(
                    "OperationalCapability",
                    goal_text,
                    structural_source_text=source_text,
                    structural_analysis_source="knowledge_graph",
                    structural_complexity_score=(
                        analysis.complexity_score if analysis is not None else 0
                    ),
                    structural_predicate_count=(
                        len(analysis.predicate_texts) if analysis is not None else 0
                    ),
                )
                goals.append((goal_id, goal_text))

            first = False

        return goals

    def capture_goal_candidates(self, goals: list[tuple[str, str]]) -> None:
        """Discover explicit structural mentions without semantic LLM extraction."""

        seen_mentions: set[str] = {
            self.model.name(node_id).strip().casefold()
            for node_id in self.model.participants()
        }

        for goal_id, goal_text in goals:
            analysis = self._analyze_capability(goal_text)
            if analysis is None:
                continue

            for mention in analysis.mentions:
                normalized_key = mention.text.strip().casefold()
                if not normalized_key or normalized_key in seen_mentions:
                    continue
                seen_mentions.add(normalized_key)

                if not self.ask_yes_no(
                    f'You mentioned "{mention.text}". Should it be included in the operational picture?',
                    (
                        "The structural Knowledge Graph found an explicit noun phrase that "
                        "may represent a participant or context element. Nothing is added "
                        "unless you confirm it."
                    ),
                ):
                    continue

                decision = self.confirm_participant_classification(
                    mention.text,
                    advisory_type=mention.suggested_concept,
                    advisory_nature=mention.suggested_nature,
                    advisory_reason=(
                        "Candidate supplied by configured lexical Knowledge Graph data."
                        if mention.source == "lexical_knowledge"
                        else "Candidate supplied by domain-neutral structural analysis."
                    ),
                    advisory_source="knowledge_graph_capability_mention",
                )
                if decision is None:
                    continue

                node_type, normalized_name, classification = decision
                expects_activity = self.activity_expectation_for(
                    node_type,
                    normalized_name,
                )
                node_id = self.add_node(
                    node_type,
                    normalized_name,
                    expects_activity=expects_activity,
                    discovery_source="knowledge_graph_capability_mention",
                    discovered_from_goal=goal_id,
                    original_mention=mention.text,
                    mention_source=mention.source,
                    **classification,
                )
                if node_id:
                    self.add_notice(
                        f"Candidate from goal confirmed: {normalized_name}"
                    )
