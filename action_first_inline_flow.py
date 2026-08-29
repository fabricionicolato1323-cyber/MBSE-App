from __future__ import annotations

from semantic_frames import (
    format_frame_summary,
    frame_is_complex,
    looks_structurally_complex,
    parse_activity_frames,
    parse_simple_activity_frame,
)
from validator import (
    normalize_whitespace,
    obvious_non_english_short_text,
    reconcile_activity_frame_solution_bias,
    validate_llm_candidate,
)


class ActionFirstInlineCreationMixin:
    """Create an inline action before asking which participant performs it."""

    def _capture_inline_action_text(self) -> str:
        self.current_why = (
            "Describe the missing action first so the performer can be selected "
            "with the action already clear."
        )
        while True:
            self.draw_question(
                "What is the new action?",
                explanation=(
                    "Describe the action first. You will choose who performs it next."
                ),
                expected_structure="verb + object or complement",
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available here.")
                continue

            value = normalize_whitespace(value)
            if not value:
                self.add_notice("Enter one action before choosing its performer.")
                continue
            if len(value) > 160:
                self.add_notice("Please describe the action more briefly.")
                continue
            if obvious_non_english_short_text(value):
                self.add_notice("Please answer in English only.")
                continue
            if looks_structurally_complex(value) and self.llm is None:
                self.add_notice(
                    "This description contains multiple actions or complements. "
                    "AI assistance is unavailable, so please describe one simple "
                    "action at a time."
                )
                continue

            return value

    def _select_performer_for_inline_action(self, action_text: str) -> str | None:
        while True:
            participants = self.model.active_participants()
            choices = [(node_id, self.model.name(node_id)) for node_id in participants]
            choices.append(("__new_participant__", "+ Add new participant / context"))
            selected = self.ask_choice(
                "Who performs this action?",
                choices,
                "Every action needs an explicit real-world performer.",
                extra_lines=[f"Action: {action_text}"],
            )
            if selected != "__new_participant__":
                return selected

            participant_id = self._capture_one_participant()
            if participant_id is None:
                continue
            if not self.model.expects_activity(participant_id):
                self.add_notice(
                    "That item was kept as context and cannot perform an action. "
                    "Choose or add an active participant."
                )
                continue
            return participant_id

    def _interpret_inline_action_text(
        self,
        performer_id: str,
        source_text: str,
    ) -> dict | None:
        participant_name = self.model.name(performer_id)
        known_subjects = [
            self.model.name(node_id)
            for node_id in self.model.participants()
        ]

        if not looks_structurally_complex(source_text):
            frame_result = parse_simple_activity_frame(
                source_text,
                default_subject=participant_name,
            )
        elif self.llm is None:
            self.add_notice(
                "Please rewrite the action as one simple action. Nothing was added."
            )
            return None
        else:
            try:
                with self.ollama_operation(
                    "Analyzing action structure with Ollama"
                ) as llm:
                    frame_result = parse_activity_frames(
                        llm,
                        source_text,
                        default_subject=participant_name,
                        known_subjects=known_subjects,
                        context=self.model.short_context(),
                    )
            except Exception as exc:
                self.add_notice(
                    f"I could not analyze the action structure: {exc}\n"
                    "Please rewrite it as one simple action. Nothing was added."
                )
                return None

        frame_result = reconcile_activity_frame_solution_bias(
            source_text,
            frame_result,
        )

        if frame_result.get("language") == "Non-English":
            self.add_notice(
                "Please answer in English only. Nothing was added to the model."
            )
            return None

        if frame_result.get("solution_bias", False):
            self.add_notice(
                "That answer appears to describe a technical implementation rather "
                "than operational behavior. Nothing was added."
            )
            return None

        if not frame_result.get("valid", False):
            reason = frame_result.get("reason") or (
                "I could not identify a usable operational action."
            )
            self.add_notice(
                f"I cannot use that action yet.\nReason: {reason}\n"
                "Nothing was added to the model."
            )
            return None

        for clause in frame_result.get("clauses", []):
            activity_text = clause.get("activity_text", "")
            synthetic_result = {
                "valid": True,
                "language": frame_result.get("language", "English"),
                "detected_concept": "OperationalActivity",
                "normalized_value": activity_text,
                "solution_bias": False,
                "reason": "",
                "suggestion": "",
            }
            validated = validate_llm_candidate(
                activity_text,
                "OperationalActivity",
                synthetic_result,
            )
            if not validated.accepted:
                self.add_notice(
                    f"I cannot use that action structure yet.\n"
                    f"Reason: {validated.reason}\n"
                    "Nothing was added to the model."
                )
                return None
            clause["activity_text"] = validated.normalized_value

        complex_input = (
            looks_structurally_complex(source_text)
            or frame_is_complex(frame_result)
        )
        if complex_input:
            self.show_command_page(
                "ACTION INTERPRETATION",
                format_frame_summary(frame_result),
            )
            if not self.ask_yes_no(
                "Use this interpretation?",
                "No activity is written to the model until you confirm the "
                "decomposition of this complex action description.",
            ):
                self.add_notice(
                    "Interpretation rejected. Please rewrite the action description."
                )
                return None

        return frame_result

    def _create_new_action_reference(self) -> str | None:
        while True:
            source_text = self._capture_inline_action_text()

            performer_id = self._select_performer_for_inline_action(source_text)
            if performer_id is None:
                return None

            frame_result = self._interpret_inline_action_text(
                performer_id,
                source_text,
            )
            if frame_result is not None:
                break

        created: list[str] = []
        for clause in frame_result.get("clauses", []):
            action_id = self.create_activity_from_frame(
                clause,
                performer_id,
                source_text,
            )
            if action_id and action_id not in created:
                created.append(action_id)

        if not created:
            self.add_notice("No new action was created.")
            return None
        if len(created) == 1:
            return created[0]
        return self.ask_number(
            "Which new action should be used here?",
            created,
            self.model.action_label,
            "Choose the newly created action that belongs in the interrupted relationship.",
        )
