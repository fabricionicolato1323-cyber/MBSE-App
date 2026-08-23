from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable

from candidate_discovery import extract_goal_candidates
from graph_model import OAGraph
from knowledge_graph import ArcadiaKnowledgeBase
from llm_service import LocalLLM
from semantic_frames import (
    format_frame_summary,
    frame_is_complex,
    looks_structurally_complex,
    parse_activity_frames,
)
from terminal_ui import EXPECTED_STRUCTURES, processing_indicator
from validator import validate_llm_candidate, validate_participant_candidate

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_SAVE_PATH = BASE_DIR / "oa_model.json"
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"

COMMAND_BAR = (
    "/help  /ask QUESTION  /compare  /show  /check  /why  "
    "/save  /undo  /clc  /done  /quit"
)

HELP_TEXT = """
Commands:
  /help   Show commands
  /ask QUESTION
          Ask an Arcadia method question using only knowledge-graph evidence
  /compare
          Compare the current model with the RDF/SHACL Arcadia rules
  /show   Show the model so far
  /check  Check for obvious gaps
  /why    Explain why the current question matters
  /save   Save the model now
  /undo   Undo the last accepted model change
  /clc    Clear the terminal screen
  /done   Finish and save
  /quit   Exit

Each question also shows the preferred answer structure.
The structure is guidance, not a rigid template.
Activity answers may contain multiple subjects, objects, complements, or actions.
Complex activity sentences are decomposed before anything is written to the model.
Knowledge answers are read-only: they cannot add or change model elements.
If the graph has no evidence, the assistant abstains instead of using model memory.
""".strip()


class OAApp:
    def __init__(self) -> None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        model_path = Path(config["model_path"])
        if not model_path.is_absolute():
            model_path = BASE_DIR / model_path

        with processing_indicator("Loading Arcadia knowledge graph"):
            self.knowledge = ArcadiaKnowledgeBase(KNOWLEDGE_BASE_DIR)

        with processing_indicator("Loading local AI model"):
            self.llm = LocalLLM(
                model_path=str(model_path),
                n_ctx=config.get("n_ctx", 4096),
                n_threads=config.get("n_threads"),
                n_gpu_layers=config.get("n_gpu_layers", 0),
                chat_format=config.get("chat_format") or None,
            )

        self.model = OAGraph()
        self.current_why = (
            "This helps build the operational picture one small step at a time."
        )
        self.notice = ""

    # ------------------------------------------------------------------
    # Terminal UI
    # ------------------------------------------------------------------
    @staticmethod
    def clear_screen() -> None:
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def pause() -> None:
        input("\nPress Enter to return to the current question...")

    def add_notice(self, message: str) -> None:
        if not message:
            return
        self.notice = (
            f"{self.notice}\n{message}".strip()
            if self.notice
            else message
        )

    def draw_question(
        self,
        question: str,
        explanation: str = "",
        example: str = "",
        expected_structure: str = "",
        extra_lines: list[str] | None = None,
    ) -> None:
        # Preserve terminal history. /clc is the only command that clears it.
        print()
        print("=" * 72)
        print("GUIDED OPERATIONAL MODEL BUILDER")
        print("=" * 72)
        print(f"Commands: {COMMAND_BAR}")
        print("-" * 72)

        if self.notice:
            print(self.notice)
            print("-" * 72)
            self.notice = ""

        print(question)
        if expected_structure:
            print(f"  Expected answer: {expected_structure}")
        if explanation:
            print(f"  {explanation}")
        if example:
            print(f"  Example: {example}")
        if extra_lines:
            for line in extra_lines:
                print(line)
        print()

    def show_command_page(self, title: str, body: str) -> None:
        print()
        print("=" * 72)
        print(title)
        print("=" * 72)
        print(body)
        self.pause()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def command(self, value: str) -> bool:
        raw = value.strip()
        cmd = raw.casefold()
        if not cmd.startswith("/"):
            return False

        if cmd == "/help":
            self.show_command_page("HELP", HELP_TEXT)
        elif cmd == "/ask":
            self.add_notice(
                "Add an English Arcadia question after the command.\n"
                "Example: /ask What is the difference between an actor and an entity?"
            )
        elif cmd.startswith("/ask "):
            question = raw[5:].strip()
            if not question:
                self.add_notice("Please add a question after /ask.")
            else:
                with processing_indicator("Querying the Arcadia knowledge graph"):
                    answer = self.knowledge.answer(question, self.llm)
                self.show_command_page("ARCADIA KNOWLEDGE ANSWER", answer)
        elif cmd == "/compare":
            with processing_indicator("Comparing model with Arcadia rules"):
                comparison = self.knowledge.compare_model(self.model)
            self.show_command_page(
                "ARCADIA KNOWLEDGE GRAPH COMPARISON",
                self.knowledge.format_comparison(comparison),
            )
        elif cmd == "/show":
            self.show_command_page("MODEL SO FAR", self.model.friendly_show())
        elif cmd == "/check":
            notes = self.model.completeness_messages()
            body = (
                "\n".join(f"- {note}" for note in notes)
                if notes
                else "No obvious gap was found in the current model."
            )
            self.show_command_page("MODEL CHECK", body)
        elif cmd == "/why":
            self.show_command_page(
                "WHY THIS QUESTION MATTERS",
                self.current_why,
            )
        elif cmd == "/save":
            path = self.model.save(str(DEFAULT_SAVE_PATH))
            self.add_notice(f"Saved: {path}")
        elif cmd == "/undo":
            self.add_notice(
                "Last change undone."
                if self.model.undo()
                else "There is nothing to undo."
            )
        elif cmd == "/clc":
            self.clear_screen()
            self.notice = ""
        elif cmd == "/done":
            path = self.model.save(str(DEFAULT_SAVE_PATH))
            print(f"\nSaved: {path}")
            print("Finished.")
            raise SystemExit(0)
        elif cmd == "/quit":
            print("\nExiting.")
            raise SystemExit(0)
        else:
            self.add_notice("Unknown command. Type /help.")
        return True

    # ------------------------------------------------------------------
    # Generic input helpers
    # ------------------------------------------------------------------
    def ask_yes_no(self, question: str, why: str) -> bool:
        self.current_why = why
        while True:
            self.draw_question(
                f"{question} (yes/no)",
                explanation="Answer only 'yes' or 'no'.",
                expected_structure=EXPECTED_STRUCTURES["yes_no"],
            )
            value = input("> ").strip()
            if self.command(value):
                continue

            lowered = value.casefold()
            if lowered in {"yes", "y"}:
                return True
            if lowered in {"no", "n"}:
                return False

            self.add_notice("Please answer only 'yes' or 'no'.")

    def ask_number(
        self,
        question: str,
        node_ids: list[str],
        label: Callable[[str], str],
        why: str,
    ) -> str:
        self.current_why = why
        while True:
            lines = [
                f"  {index}. {label(node_id)}"
                for index, node_id in enumerate(node_ids, start=1)
            ]
            self.draw_question(
                question,
                explanation="Choose one of the numbers below.",
                expected_structure=EXPECTED_STRUCTURES["number"],
                extra_lines=lines,
            )
            value = input("> ").strip()
            if self.command(value):
                continue

            try:
                selected = int(value) - 1
                if 0 <= selected < len(node_ids):
                    return node_ids[selected]
            except ValueError:
                pass

            self.add_notice("Please select one of the numbers shown.")

    def ask_validated(
        self,
        question: str,
        explanation: str,
        example: str,
        expected_concept: str,
        why: str,
        context: str = "",
    ) -> str:
        self.current_why = why

        while True:
            self.draw_question(
                question,
                explanation,
                example,
                expected_structure=EXPECTED_STRUCTURES.get(
                    expected_concept,
                    "Short English phrase",
                ),
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available here.")
                continue

            try:
                with processing_indicator("Processing answer with local AI"):
                    llm_result = self.llm.validate_candidate(
                        candidate=value,
                        expected_concept=expected_concept,
                        context=context or self.model.short_context(),
                    )
            except Exception:
                self.add_notice(
                    "I had trouble reading the local model response.\n"
                    "Please try the same answer once more. Nothing was added."
                )
                continue

            result = validate_llm_candidate(
                value,
                expected_concept,
                llm_result,
            )
            if result.accepted:
                normalized = result.normalized_value
                if normalized and normalized.casefold() != value.casefold():
                    self.add_notice(
                        f'English suggestion: "{normalized}"\n'
                        "Your meaning was clear, so I will use the corrected wording."
                    )
                return normalized

            message = (
                f"I cannot use that answer yet.\n"
                f"Reason: {result.reason}"
            )
            if result.suggestion:
                message += f"\nTry: {result.suggestion}"
            message += "\nNothing was added to the model."
            self.add_notice(message)

    def ask_participant(self) -> tuple[str, str]:
        self.current_why = (
            "The model needs the people, roles, organizations, groups, "
            "facilities, places, resources, and other real-world elements "
            "involved in the operation."
        )

        while True:
            self.draw_question(
                "Who or what is involved?",
                explanation=(
                    "Name one person, role, organization, group, facility, "
                    "place, resource, or other real-world element involved."
                ),
                example="Operations Coordinator",
                expected_structure=EXPECTED_STRUCTURES["participant"],
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available here.")
                continue

            try:
                with processing_indicator("Classifying with local AI"):
                    llm_result = self.llm.validate_participant(
                        value,
                        self.model.short_context(),
                    )
            except Exception:
                self.add_notice(
                    "I had trouble reading the local model response.\n"
                    "Please try the same answer once more. Nothing was added."
                )
                continue

            result = validate_participant_candidate(value, llm_result)
            if result.accepted:
                if (
                    result.normalized_value
                    and result.normalized_value.casefold() != value.casefold()
                ):
                    self.add_notice(
                        f'English suggestion: "{result.normalized_value}"\n'
                        "Your meaning was clear, so I will use the corrected wording."
                    )
                return result.detected_concept, result.normalized_value

            message = (
                f"I cannot use that answer yet.\n"
                f"Reason: {result.reason}"
            )
            if result.suggestion:
                message += f"\nTry: {result.suggestion}"
            message += "\nNothing was added to the model."
            self.add_notice(message)

    # ------------------------------------------------------------------
    # Graph helpers
    # ------------------------------------------------------------------
    def add_node(
        self,
        node_type: str,
        name: str,
        *,
        expects_activity: bool | None = None,
        **attributes,
    ) -> str:
        ok, node_id, error = self.model.add_node(
            node_type,
            name,
            expects_activity=expects_activity,
            **attributes,
        )
        if not ok:
            self.add_notice(f"Not added: {error}")
            return node_id

        self.add_notice(f"Added: {name}")
        return node_id

    def link_action_to_goal(self, action_id: str) -> None:
        goals = self.model.nodes_of_type("OperationalCapability")
        if not goals:
            return

        if any(
            self.model.has_relation(
                action_id,
                "SUPPORTS_CAPABILITY",
                goal_id,
            )
            for goal_id in goals
        ):
            return

        if len(goals) == 1:
            goal_id = goals[0]
        else:
            goal_id = self.ask_number(
                "Which goal does this action help achieve?",
                goals,
                self.model.name,
                "This connects each action to the outcome it helps achieve.",
            )

        ok, error = self.model.add_relation(
            action_id,
            "SUPPORTS_CAPABILITY",
            goal_id,
        )
        if not ok:
            self.add_notice(
                f"Could not connect the action to the goal: {error}"
            )

    def activity_expectation_for(
        self,
        node_type: str,
        name: str,
    ) -> bool:
        if node_type == "OperationalActor":
            return True

        return self.ask_yes_no(
            f"Does {name} actively do something in this operation?",
            "Some real-world elements perform actions, while others may "
            "only provide operational context.",
        )

    # ------------------------------------------------------------------
    # Semantic activity parsing
    # ------------------------------------------------------------------
    def ask_activity_frames(
        self,
        participant_id: str,
    ) -> tuple[str, dict]:
        participant_name = self.model.name(participant_id)
        self.current_why = (
            "The action structure identifies who performs each behavior, the "
            "main verb, its objects, and any recipients, locations, conditions, "
            "or timing without forcing the user to enter one rigid template."
        )

        while True:
            self.draw_question(
                f"What does {participant_name} do?",
                explanation=(
                    "You may describe one action or a natural sentence with "
                    "multiple subjects, objects, complements, or actions."
                ),
                example=(
                    "Coordinate service requests and report status to operations"
                ),
                expected_structure=EXPECTED_STRUCTURES["OperationalActivity"],
            )
            value = input("> ").strip()

            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available here.")
                continue
            if not value:
                self.add_notice("The answer cannot be empty.")
                continue

            known_subjects = [
                self.model.name(node_id)
                for node_id in self.model.participants()
            ]

            try:
                with processing_indicator(
                    "Analyzing action structure with local AI"
                ):
                    frame_result = parse_activity_frames(
                        self.llm,
                        value,
                        default_subject=participant_name,
                        known_subjects=known_subjects,
                        context=self.model.short_context(),
                    )
            except Exception:
                self.add_notice(
                    "I had trouble analyzing the action structure.\n"
                    "Please try the same answer once more. Nothing was added."
                )
                continue

            if frame_result.get("language") == "Non-English":
                self.add_notice(
                    "Please answer in English only. Nothing was added to the model."
                )
                continue

            if frame_result.get("solution_bias", False):
                self.add_notice(
                    "That answer appears to describe a technical implementation "
                    "rather than operational behavior. Nothing was added."
                )
                continue

            if not frame_result.get("valid", False):
                reason = frame_result.get("reason") or (
                    "I could not identify a usable operational action."
                )
                self.add_notice(
                    f"I cannot use that answer yet.\nReason: {reason}\n"
                    "Nothing was added to the model."
                )
                continue

            rejected_clause = ""
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
                    rejected_clause = validated.reason
                    break
                clause["activity_text"] = validated.normalized_value

            if rejected_clause:
                self.add_notice(
                    f"I cannot use that action structure yet.\n"
                    f"Reason: {rejected_clause}\n"
                    "Nothing was added to the model."
                )
                continue

            complex_input = (
                looks_structurally_complex(value)
                or frame_is_complex(frame_result)
            )
            if complex_input:
                summary = format_frame_summary(frame_result)
                self.show_command_page("ACTION INTERPRETATION", summary)
                if not self.ask_yes_no(
                    "Use this interpretation?",
                    "No activity is written to the graph until you confirm "
                    "the decomposition of this complex sentence.",
                ):
                    self.add_notice(
                        "Interpretation rejected. Please rewrite the action sentence."
                    )
                    continue

            return value, frame_result

    def resolve_frame_subjects(
        self,
        clause: dict,
        default_participant_id: str,
    ) -> list[str]:
        default_name = self.model.name(default_participant_id)
        subjects = clause.get("subjects", []) or [default_name]
        resolved: list[str] = []

        for subject in subjects:
            existing = self.model.find_participant_duplicate(subject)
            if existing:
                if existing not in resolved:
                    resolved.append(existing)
                continue

            try:
                with processing_indicator(
                    "Classifying additional subject with local AI"
                ):
                    llm_result = self.llm.validate_participant(
                        subject,
                        self.model.short_context(),
                    )
                result = validate_participant_candidate(subject, llm_result)
            except Exception:
                result = None

            if result is None or not result.accepted:
                self.add_notice(
                    f'I could not classify the additional subject "{subject}". '
                    "It was not added as a performer."
                )
                continue

            if not self.ask_yes_no(
                f'You mentioned "{subject}" as another performer. '
                "Should it be included in the operational picture?",
                "An explicitly named additional subject can become another "
                "participant performing the same action.",
            ):
                continue

            subject_id = self.add_node(
                result.detected_concept,
                result.normalized_value,
                expects_activity=True,
                discovery_source="activity_subject",
            )
            if subject_id not in resolved:
                resolved.append(subject_id)

        return resolved

    def create_activity_from_frame(
        self,
        clause: dict,
        default_participant_id: str,
        source_text: str,
    ) -> str | None:
        performers = self.resolve_frame_subjects(
            clause,
            default_participant_id,
        )
        if not performers:
            self.add_notice(
                f"Skipped '{clause.get('activity_text', '')}' because no "
                "confirmed performer could be assigned."
            )
            return None

        activity_text = clause["activity_text"]
        existing = self.model.find_duplicate(
            "OperationalActivity",
            activity_text,
        )

        attributes = {
            "semantic_frame": True,
            "semantic_verb": clause.get("verb", ""),
            "semantic_objects": clause.get("objects", []),
            "semantic_recipients": clause.get("recipients", []),
            "semantic_locations": clause.get("locations", []),
            "semantic_conditions": clause.get("conditions", []),
            "semantic_time": clause.get("time", []),
            "semantic_other_complements": clause.get(
                "other_complements",
                [],
            ),
            "source_text": source_text,
        }

        if existing:
            action_id = existing
            current_semantics = self.model.activity_semantics(action_id)
            if not current_semantics:
                self.model.update_node_attributes(action_id, **attributes)
        else:
            action_id = self.add_node(
                "OperationalActivity",
                activity_text,
                **attributes,
            )

        for performer_id in performers:
            if self.model.has_relation(
                performer_id,
                "PERFORMS",
                action_id,
            ):
                continue
            ok, error = self.model.add_relation(
                performer_id,
                "PERFORMS",
                action_id,
            )
            if not ok:
                self.add_notice(
                    f"Could not connect a performer to the action: {error}"
                )

        self.link_action_to_goal(action_id)
        return action_id

    # ------------------------------------------------------------------
    # Stage 1: goals
    # ------------------------------------------------------------------
    def capture_goals(self) -> list[tuple[str, str]]:
        goals: list[tuple[str, str]] = []
        first = True

        while first or self.ask_yes_no(
            "Is there another important goal?",
            "Some operations have more than one important outcome. "
            "Add another only if it is genuinely distinct.",
        ):
            goal = self.ask_validated(
                question=(
                    "What is the main goal?"
                    if first
                    else "What is the other goal?"
                ),
                explanation=(
                    "Describe the desired operational outcome, not a "
                    "system or implementation."
                ),
                example="Maintain safe and effective operations",
                expected_concept="OperationalCapability",
                why=(
                    "The goal gives the rest of the model a clear purpose "
                    "and helps prevent premature solution design."
                ),
            )
            goal_id = self.add_node(
                "OperationalCapability",
                goal,
            )
            goals.append((goal_id, goal))
            first = False

        return goals

    # ------------------------------------------------------------------
    # Stage 2: discover candidate participants/context from goal wording
    # ------------------------------------------------------------------
    def capture_goal_candidates(
        self,
        goals: list[tuple[str, str]],
    ) -> None:
        for goal_id, goal_text in goals:
            existing_names = [
                self.model.name(node_id)
                for node_id in self.model.participants()
            ]

            try:
                with processing_indicator(
                    "Inspecting goal with local AI"
                ):
                    candidates = extract_goal_candidates(
                        self.llm,
                        goal_text,
                        existing_names=existing_names,
                    )
            except Exception:
                self.add_notice(
                    "I could not inspect this goal for possible people "
                    "or context elements. You can still add them manually "
                    "in the next step."
                )
                continue

            for candidate in candidates:
                mention = candidate["mention"]
                proposed_type = candidate["candidate_concept"]

                if not self.ask_yes_no(
                    f'You mentioned "{mention}". Should it be included '
                    "in the operational picture?",
                    "Explicit nouns in a goal may identify people, "
                    "organizations, places, resources, or context worth "
                    "modeling. Nothing is added unless you confirm it.",
                ):
                    continue

                node_type = proposed_type
                normalized_name = mention

                try:
                    with processing_indicator(
                        "Classifying candidate with local AI"
                    ):
                        llm_result = self.llm.validate_participant(
                            mention,
                            self.model.short_context(),
                        )
                    result = validate_participant_candidate(
                        mention,
                        llm_result,
                    )
                    if result.accepted:
                        node_type = result.detected_concept
                        normalized_name = result.normalized_value
                except Exception:
                    # Candidate extraction already passed the exact-span barrier
                    # and the user confirmed it. Keep the proposed type.
                    pass

                expects_activity = self.activity_expectation_for(
                    node_type,
                    normalized_name,
                )
                node_id = self.add_node(
                    node_type,
                    normalized_name,
                    expects_activity=expects_activity,
                    discovery_source="goal_text",
                    discovered_from_goal=goal_id,
                    original_mention=mention,
                )
                if node_id:
                    self.add_notice(
                        f"Candidate from goal confirmed: {normalized_name}"
                    )

    # ------------------------------------------------------------------
    # Stage 3: participant actions + additional participants
    # ------------------------------------------------------------------
    def capture_actions_for_participant(
        self,
        participant_id: str,
    ) -> None:
        if not self.model.expects_activity(participant_id):
            return

        participant_name = self.model.name(participant_id)
        first_action = not bool(
            self.model.actions_for_participant(participant_id)
        )

        while first_action or self.ask_yes_no(
            f"Does {participant_name} do anything else?",
            "A participant may perform more than one important "
            "operational action.",
        ):
            source_text, frame_result = self.ask_activity_frames(
                participant_id
            )

            created = 0
            for clause in frame_result.get("clauses", []):
                if self.create_activity_from_frame(
                    clause,
                    participant_id,
                    source_text,
                ):
                    created += 1

            if created > 1:
                self.add_notice(
                    f"The sentence was decomposed into {created} "
                    "operational activities."
                )
            first_action = False

    def add_manual_participant(self) -> str:
        node_type, participant_name = self.ask_participant()
        expects_activity = self.activity_expectation_for(
            node_type,
            participant_name,
        )
        participant_id = self.add_node(
            node_type,
            participant_name,
            expects_activity=expects_activity,
        )

        if not expects_activity:
            self.add_notice(
                f"{participant_name} will be kept as operational context. "
                "No action is required for it."
            )

        return participant_id

    def capture_participants_and_actions(self) -> None:
        # First elaborate candidates confirmed from goal wording.
        for participant_id in list(self.model.participants()):
            self.capture_actions_for_participant(participant_id)

        if not self.model.participants():
            participant_id = self.add_manual_participant()
            self.capture_actions_for_participant(participant_id)

        while self.ask_yes_no(
            "Is anyone or anything else involved?",
            "This helps discover other people, organizations, "
            "facilities, resources, places, and environmental elements "
            "not already mentioned in the goals.",
        ):
            participant_id = self.add_manual_participant()
            self.capture_actions_for_participant(participant_id)

    # ------------------------------------------------------------------
    # Stage 4: structure and environment
    # ------------------------------------------------------------------
    def capture_structure_and_environment(self) -> None:
        participants = self.model.participants()
        entities = self.model.nodes_of_type("OperationalEntity")

        if len(participants) < 2 or not entities:
            return

        print()
        print("-" * 72)
        print(
            "I will now ask a few simple questions about how the "
            "participants are organized and where they operate."
        )

        for participant_id in list(participants):
            participant_name = self.model.name(participant_id)
            entity_candidates = [
                node_id
                for node_id in entities
                if node_id != participant_id
            ]

            if not entity_candidates:
                continue

            if self.model.structural_parent(participant_id) is None:
                if self.ask_yes_no(
                    f"Is {participant_name} part of another group, "
                    "organization, facility, or larger element already "
                    "mentioned?",
                    "This captures organizational or structural membership.",
                ):
                    parent_id = self.ask_number(
                        f"What is {participant_name} part of?",
                        entity_candidates,
                        self.model.name,
                        "Choose the larger group, organization, facility, "
                        "or element that structurally contains it.",
                    )
                    ok, error = self.model.add_relation(
                        parent_id,
                        "CONTAINS",
                        participant_id,
                    )
                    if ok:
                        self.add_notice(
                            f"Added structure: "
                            f"{self.model.name(parent_id)} contains "
                            f"{participant_name}"
                        )
                    else:
                        self.add_notice(
                            f"Could not add the structural relation: {error}"
                        )

            if not self.model.locations_for(participant_id):
                if self.ask_yes_no(
                    f"Does {participant_name} operate in or inside a "
                    "place or area already mentioned?",
                    "Location is kept separate from organizational "
                    "or structural membership.",
                ):
                    location_id = self.ask_number(
                        f"Where does {participant_name} operate?",
                        entity_candidates,
                        self.model.name,
                        "Choose the place, facility, area, or environment.",
                    )
                    ok, error = self.model.add_relation(
                        participant_id,
                        "LOCATED_IN",
                        location_id,
                    )
                    if ok:
                        self.add_notice(
                            f"Added location: {participant_name} operates in "
                            f"{self.model.name(location_id)}"
                        )
                    else:
                        self.add_notice(
                            f"Could not add the location: {error}"
                        )

    # ------------------------------------------------------------------
    # Stage 5: interactions
    # ------------------------------------------------------------------
    def capture_interactions(self) -> None:
        actions = self.model.nodes_of_type("OperationalActivity")
        if len(actions) < 2:
            return

        for source_id in list(actions):
            source_label = self.model.action_label(source_id)

            if not self.ask_yes_no(
                f"Does '{source_label}' exchange anything with another action?",
                "Interactions may carry information, material, requests, "
                "or other operational items.",
            ):
                continue

            add_more = True
            while add_more:
                item = self.ask_validated(
                    question="What is exchanged?",
                    explanation=(
                        "Name the information, material, request, or item "
                        "in a few words."
                    ),
                    example="Status information",
                    expected_concept="OperationalExchange",
                    why=(
                        "Naming what is exchanged makes the operational "
                        "interaction explicit."
                    ),
                    context=(
                        f"Source action: {source_label}. "
                        f"{self.model.short_context()}"
                    ),
                )

                targets = [
                    node_id
                    for node_id in actions
                    if node_id != source_id
                ]
                target_id = self.ask_number(
                    "Which action receives it?",
                    targets,
                    self.model.action_label,
                    "The receiver identifies where this interaction goes next.",
                )

                ok, error = self.model.add_relation(
                    source_id,
                    "OPERATIONAL_EXCHANGE",
                    target_id,
                    name=item,
                )
                if ok:
                    self.add_notice(f"Added interaction: {item}")
                else:
                    self.add_notice(
                        f"Could not add the interaction: {error}"
                    )

                add_more = self.ask_yes_no(
                    f"Is anything else exchanged from '{source_label}'?",
                    "Add another item only when it is a distinct "
                    "operational interaction.",
                )

    # ------------------------------------------------------------------
    # Stage 6: communication
    # ------------------------------------------------------------------
    def capture_communication(self) -> None:
        for (
            source_action,
            target_action,
            exchange_name,
        ) in self.model.exchanges():
            source_participants = self.model.participants_for_activity(
                source_action
            )
            target_participants = self.model.participants_for_activity(
                target_action
            )

            for source_participant in source_participants:
                for target_participant in target_participants:
                    if source_participant == target_participant:
                        continue
                    if self.model.has_communication_between(
                        source_participant,
                        target_participant,
                    ):
                        continue

                    source_name = self.model.name(source_participant)
                    target_name = self.model.name(target_participant)

                    if not self.ask_yes_no(
                        f"Do {source_name} and {target_name} use a "
                        f"communication method for '{exchange_name}'?",
                        "If the interaction crosses between different "
                        "participants, the communication method may be "
                        "important operationally.",
                    ):
                        continue

                    medium = self.ask_validated(
                        question="How do they communicate?",
                        explanation=(
                            "Name the real-world communication method, "
                            "not software or implementation details."
                        ),
                        example="Direct communication",
                        expected_concept="CommunicationMean",
                        why=(
                            "This records how two operational participants "
                            "are able to interact."
                        ),
                        context=(
                            f"Participants: {source_name} and {target_name}. "
                            f"Interaction: {exchange_name}."
                        ),
                    )

                    ok, error = self.model.add_relation(
                        source_participant,
                        "COMMUNICATION_MEAN",
                        target_participant,
                        name=medium,
                    )
                    if ok:
                        self.add_notice(
                            f"Added communication method: {medium}"
                        )
                    else:
                        self.add_notice(
                            f"Could not add the communication method: {error}"
                        )

    def run(self) -> None:
        goals = self.capture_goals()
        self.capture_goal_candidates(goals)
        self.capture_participants_and_actions()
        self.capture_structure_and_environment()
        self.capture_interactions()
        self.capture_communication()

        print()
        print("=" * 72)
        print("MODEL COMPLETE")
        print("=" * 72)
        print(self.model.friendly_show())

        notes = self.model.completeness_messages()
        if notes:
            print("\nA few things may still need attention:")
            for note in notes:
                print(f"- {note}")
        else:
            print("\nThe model has no obvious basic gaps.")

        with processing_indicator("Comparing model with Arcadia rules"):
            comparison = self.knowledge.compare_model(self.model)
        print("\nKnowledge graph comparison:")
        print(self.knowledge.format_comparison(comparison, max_issues=8))

        path = self.model.save(str(DEFAULT_SAVE_PATH))
        print(f"\nSaved: {path}")
        print("Finished.")


def main() -> None:
    try:
        OAApp().run()
    except KeyboardInterrupt:
        print("\nInterrupted. The unfinished answer was not added.")
        sys.exit(130)
    except FileNotFoundError as exc:
        print(exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
