from __future__ import annotations

import re

from semantic_frames import looks_structurally_complex, parse_activity_frames, parse_simple_activity_frame
from terminal_ui import EXPECTED_STRUCTURES
from validator import normalize_whitespace


class MinimalInputPolicyMixin:
    """Keep user-input checks structural and non-blocking on wording.

    The guided flow may still enforce the shape required by the current UI step
    (for example a non-empty text value, a yes/no response, or a numbered
    selection). It must not reject free-text answers because of vocabulary,
    semantic interpretation, solution-bias guesses, concept guesses, or language
    classification. Free text is preserved apart from whitespace normalization.
    """

    @staticmethod
    def _fallback_activity_frame(value: str, participant_name: str) -> dict:
        normalized = normalize_whitespace(value)
        words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]*", normalized)
        verb = words[0] if words else normalized
        return {
            "valid": True,
            "language": "Language-neutral",
            "solution_bias": False,
            "reason": "",
            "clauses": [
                {
                    "subjects": [participant_name] if participant_name else [],
                    "verb": verb,
                    "objects": [],
                    "recipients": [],
                    "locations": [],
                    "conditions": [],
                    "time": [],
                    "other_complements": [],
                    "activity_text": normalized,
                }
            ],
            "parsing_source": "minimal_structural_fallback",
        }

    @staticmethod
    def _sanitize_activity_frame(frame_result: object, value: str, participant_name: str) -> dict:
        """Keep usable decomposition, but never let semantic labels block input."""
        normalized = normalize_whitespace(value)
        if not isinstance(frame_result, dict):
            return MinimalInputPolicyMixin._fallback_activity_frame(normalized, participant_name)

        raw_clauses = frame_result.get("clauses")
        clauses: list[dict] = []
        if isinstance(raw_clauses, list):
            for raw_clause in raw_clauses:
                if not isinstance(raw_clause, dict):
                    continue
                activity_text = normalize_whitespace(str(raw_clause.get("activity_text") or ""))
                if not activity_text:
                    continue
                words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]*", activity_text)
                subjects = raw_clause.get("subjects")
                if not isinstance(subjects, list) or not any(str(item).strip() for item in subjects):
                    subjects = [participant_name] if participant_name else []
                clause = {
                    "subjects": [normalize_whitespace(str(item)) for item in subjects if str(item).strip()],
                    "verb": normalize_whitespace(str(raw_clause.get("verb") or (words[0] if words else activity_text))),
                    "objects": list(raw_clause.get("objects") or []) if isinstance(raw_clause.get("objects"), list) else [],
                    "recipients": list(raw_clause.get("recipients") or []) if isinstance(raw_clause.get("recipients"), list) else [],
                    "locations": list(raw_clause.get("locations") or []) if isinstance(raw_clause.get("locations"), list) else [],
                    "conditions": list(raw_clause.get("conditions") or []) if isinstance(raw_clause.get("conditions"), list) else [],
                    "time": list(raw_clause.get("time") or []) if isinstance(raw_clause.get("time"), list) else [],
                    "other_complements": list(raw_clause.get("other_complements") or []) if isinstance(raw_clause.get("other_complements"), list) else [],
                    "activity_text": activity_text,
                }
                clauses.append(clause)

        if not clauses:
            return MinimalInputPolicyMixin._fallback_activity_frame(normalized, participant_name)

        return {
            "valid": True,
            "language": "Language-neutral",
            "solution_bias": False,
            "reason": "",
            "clauses": clauses,
            "parsing_source": str(frame_result.get("parsing_source") or "non_blocking_parser"),
        }

    def ask_validated(
        self,
        question: str,
        explanation: str,
        example: str = "",
        expected_concept: str = "",
        why: str = "",
        context: str = "",
    ) -> str:
        """Accept free text after only the minimum structural checks.

        `expected_concept` and `context` remain part of the public signature for
        compatibility with the existing guided flows, but they are not used to
        judge the user's wording.
        """
        del context
        self.current_why = why

        while True:
            self.draw_question(
                question,
                explanation,
                example,
                expected_structure=EXPECTED_STRUCTURES.get(
                    expected_concept,
                    "Short text",
                ),
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available in this step.")
                continue

            normalized = normalize_whitespace(value)
            if not normalized:
                self.add_notice("Please enter a value.")
                continue

            # Do not classify, score, suggest, or reject the user's wording.
            return normalized

    def ask_participant(self) -> tuple[str, str, dict]:
        """Capture a participant name without semantic or vocabulary filtering."""
        self.current_why = (
            "The model needs the people, roles, organizations, groups, facilities, "
            "places, resources, and other real-world elements involved in the operation."
        )

        while True:
            self.draw_question(
                "Who or what is involved?",
                explanation="Name one operational participant.",
                expected_structure=EXPECTED_STRUCTURES["participant"],
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available in this step.")
                continue

            normalized = normalize_whitespace(value)
            if not normalized:
                self.add_notice("Please enter a participant name.")
                continue

            decision = self.confirm_participant_classification(normalized)
            if decision is not None:
                return decision

    def ask_additional_participant(self) -> str | None:
        """Accept any non-empty participant label, plus the structural `done` token."""
        self.current_why = (
            "The model may need people, roles, organizations, groups, facilities, "
            "places, resources, or other real-world elements involved in the operation."
        )

        while True:
            has_participants = bool(self.model.participants())
            self.draw_question(
                "Who or what else is involved?" if has_participants else "Who or what is involved?",
                explanation="Name one participant/context element, or type 'done' when finished.",
                expected_structure="participant/context name or 'done'",
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available in this step.")
                continue

            normalized = normalize_whitespace(value)
            if normalized.casefold() == "done":
                return None
            if not normalized:
                self.add_notice("Enter one participant/context name or type 'done'.")
                continue

            decision = self.confirm_participant_classification(normalized)
            if decision is None:
                continue

            node_type, participant_name, classification = decision
            expects_activity = self.activity_expectation_for(node_type, participant_name)
            participant_id = self.add_node(
                node_type,
                participant_name,
                expects_activity=expects_activity,
                **classification,
            )
            return participant_id

    def ask_activity_frames(self, participant_id: str) -> tuple[str, dict]:
        """Parse activity structure without rejecting the user's vocabulary.

        A local AI parser may decompose a complex sentence when available. If it
        is unavailable, fails, or returns no usable clauses, the complete user
        text is retained as one activity instead of blocking progress.
        """
        participant_name = self.model.name(participant_id)
        self.current_why = (
            "The action structure identifies who performs each behavior and keeps "
            "any usable decomposition without judging the vocabulary used."
        )

        while True:
            self.draw_question(
                f"What does {participant_name} do?",
                explanation=(
                    "Describe one action or a natural sentence. The wording itself "
                    "will not be rejected."
                ),
                expected_structure=EXPECTED_STRUCTURES["OperationalActivity"],
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available in this step.")
                continue

            normalized = normalize_whitespace(value)
            if not normalized:
                self.add_notice("Please enter an activity.")
                continue

            frame_result = None
            if not looks_structurally_complex(normalized):
                frame_result = parse_simple_activity_frame(
                    normalized,
                    default_subject=participant_name,
                )
            elif self.llm is not None:
                known_subjects = [
                    self.model.name(node_id)
                    for node_id in self.model.participants()
                ]
                try:
                    with self.ollama_operation("Analyzing action structure with Ollama") as llm:
                        frame_result = parse_activity_frames(
                            llm,
                            normalized,
                            default_subject=participant_name,
                            known_subjects=known_subjects,
                            context=self.model.short_context(),
                        )
                except Exception:
                    # Parsing support is optional. A parser failure must never make
                    # otherwise well-formed user text invalid.
                    frame_result = None

            return normalized, self._sanitize_activity_frame(
                frame_result,
                normalized,
                participant_name,
            )
