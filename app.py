from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable

from graph_model import OAGraph
from llm_service import LocalLLM
from validator import validate_llm_candidate, validate_participant_candidate

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_SAVE_PATH = BASE_DIR / "oa_model.json"

COMMAND_BAR = "/help  /show  /check  /why  /save  /undo  /done  /quit"

HELP_TEXT = """
Commands:
  /help   Show commands
  /show   Show the model so far
  /check  Check for obvious gaps
  /why    Explain why the current question matters
  /save   Save the model now
  /undo   Undo the last accepted model change
  /done   Finish and save
  /quit   Exit
""".strip()


class OAApp:
    def __init__(self) -> None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        model_path = Path(config["model_path"])
        if not model_path.is_absolute():
            model_path = BASE_DIR / model_path

        print("Loading local model...")
        self.llm = LocalLLM(
            model_path=str(model_path),
            n_ctx=config.get("n_ctx", 4096),
            n_threads=config.get("n_threads"),
            n_gpu_layers=config.get("n_gpu_layers", 0),
            chat_format=config.get("chat_format") or None,
        )
        self.model = OAGraph()
        self.current_why = "This helps build the operational picture one small step at a time."
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
        self.notice = f"{self.notice}\n{message}".strip() if self.notice else message

    def draw_question(
        self,
        question: str,
        explanation: str = "",
        example: str = "",
        extra_lines: list[str] | None = None,
    ) -> None:
        self.clear_screen()
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
        if explanation:
            print(f"  {explanation}")
        if example:
            print(f"  Example: {example}")
        if extra_lines:
            for line in extra_lines:
                print(line)
        print()

    def show_command_page(self, title: str, body: str) -> None:
        self.clear_screen()
        print("=" * 72)
        print(title)
        print("=" * 72)
        print(body)
        self.pause()

    # ------------------------------------------------------------------
    # Global commands
    # ------------------------------------------------------------------
    def command(self, value: str) -> bool:
        cmd = value.strip().lower()
        if not cmd.startswith("/"):
            return False

        if cmd == "/help":
            self.show_command_page("HELP", HELP_TEXT)
        elif cmd == "/show":
            self.show_command_page("MODEL SO FAR", self.model.friendly_show())
        elif cmd == "/check":
            notes = self.model.completeness_messages()
            body = "\n".join(f"- {note}" for note in notes) if notes else "No obvious gap was found in the current model."
            self.show_command_page("MODEL CHECK", body)
        elif cmd == "/why":
            self.show_command_page("WHY THIS QUESTION MATTERS", self.current_why)
        elif cmd == "/save":
            path = self.model.save(str(DEFAULT_SAVE_PATH))
            self.add_notice(f"Saved: {path}")
        elif cmd == "/undo":
            self.add_notice("Last change undone." if self.model.undo() else "There is nothing to undo.")
        elif cmd == "/done":
            path = self.model.save(str(DEFAULT_SAVE_PATH))
            self.clear_screen()
            print(f"Saved: {path}")
            print("Finished.")
            raise SystemExit(0)
        elif cmd == "/quit":
            self.clear_screen()
            print("Exiting.")
            raise SystemExit(0)
        else:
            self.add_notice("Unknown command. Type /help.")
        return True

    # ------------------------------------------------------------------
    # Small user-facing input helpers
    # ------------------------------------------------------------------
    def ask_yes_no(self, question: str, why: str) -> bool:
        self.current_why = why
        while True:
            self.draw_question(
                f"{question} (yes/no)",
                explanation="Answer only 'yes' or 'no'.",
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
            lines = [f"  {index}. {label(node_id)}" for index, node_id in enumerate(node_ids, start=1)]
            self.draw_question(
                question,
                explanation="Choose one of the numbers below.",
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
            self.draw_question(question, explanation, example)

            value = input("> ").strip()
            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available here.")
                continue

            try:
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

            result = validate_llm_candidate(value, expected_concept, llm_result)
            if result.accepted:
                normalized = result.normalized_value
                if normalized and normalized.casefold() != value.casefold():
                    self.add_notice(
                        f'English suggestion: "{normalized}"\n'
                        "Your meaning was clear, so I will use the corrected wording."
                    )
                return normalized

            message = f"I cannot use that answer yet.\nReason: {result.reason}"
            if result.suggestion:
                message += f"\nTry: {result.suggestion}"
            message += "\nNothing was added to the model."
            self.add_notice(message)

    def ask_participant(self) -> tuple[str, str]:
        self.current_why = (
            "A good operational picture needs the people, roles, organizations, groups, "
            "facilities, or other real-world parties that take part in the operation."
        )
        while True:
            self.draw_question(
                "Who or what is involved?",
                explanation=(
                    "Name one person, role, organization, group, facility, "
                    "or other real-world participant."
                ),
                example="Air Traffic Controller",
            )
            value = input("> ").strip()
            if self.command(value):
                continue
            if value.startswith("/"):
                self.add_notice("That command is not available here.")
                continue

            try:
                llm_result = self.llm.validate_participant(value, self.model.short_context())
            except Exception:
                self.add_notice(
                    "I had trouble reading the local model response.\n"
                    "Please try the same answer once more. Nothing was added."
                )
                continue

            result = validate_participant_candidate(value, llm_result)
            if result.accepted:
                if result.normalized_value and result.normalized_value.casefold() != value.casefold():
                    self.add_notice(
                        f'English suggestion: "{result.normalized_value}"\n'
                        "Your meaning was clear, so I will use the corrected wording."
                    )
                return result.detected_concept, result.normalized_value

            message = f"I cannot use that answer yet.\nReason: {result.reason}"
            if result.suggestion:
                message += f"\nTry: {result.suggestion}"
            message += "\nNothing was added to the model."
            self.add_notice(message)

    # ------------------------------------------------------------------
    # Graph write helpers
    # ------------------------------------------------------------------
    def add_node(self, node_type: str, name: str) -> str:
        ok, node_id, error = self.model.add_node(node_type, name)
        if not ok:
            self.add_notice(f"Not added: {error}")
            return node_id
        self.add_notice(f"Added: {name}")
        return node_id

    def link_action_to_goal(self, action_id: str) -> None:
        goals = self.model.nodes_of_type("OperationalCapability")
        if not goals:
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
        ok, error = self.model.add_relation(action_id, "SUPPORTS_CAPABILITY", goal_id)
        if not ok:
            self.add_notice(f"Could not connect the action to the goal: {error}")

    # ------------------------------------------------------------------
    # Guided construction
    # ------------------------------------------------------------------
    def capture_goals(self) -> None:
        first = True
        while first or self.ask_yes_no(
            "Is there another important goal?",
            "Some operations have more than one important outcome. Add another only if it is genuinely distinct.",
        ):
            goal = self.ask_validated(
                question="What is the main goal?" if first else "What is the other goal?",
                explanation="Describe the outcome people need, not the system or solution to be built.",
                example="Keep restricted airspace safe",
                expected_concept="OperationalCapability",
                why="The goal gives the rest of the model a clear purpose and helps prevent premature solution design.",
            )
            self.add_node("OperationalCapability", goal)
            first = False

    def capture_participants_and_actions(self) -> None:
        first_participant = True
        while first_participant or self.ask_yes_no(
            "Is anyone or anything else involved?",
            "This helps discover the other parties needed to understand the operation end to end.",
        ):
            node_type, participant_name = self.ask_participant()
            participant_id = self.add_node(node_type, participant_name)

            first_action = True
            while first_action or self.ask_yes_no(
                f"Does {participant_name} do anything else?",
                "A participant may perform more than one important operational action.",
            ):
                action = self.ask_validated(
                    question=f"What does {participant_name} do?",
                    explanation=(
                        "Use one short action in English. Simple wording is fine; "
                        "grammar does not need to be perfect."
                    ),
                    example="Assess incoming threat information",
                    expected_concept="OperationalActivity",
                    why="Actions show how each participant contributes to the operational goal.",
                    context=f"Participant: {participant_name}. {self.model.short_context()}",
                )
                action_id = self.add_node("OperationalActivity", action)
                ok, error = self.model.add_relation(participant_id, "PERFORMS", action_id)
                if not ok:
                    self.add_notice(f"Could not connect the action: {error}")
                self.link_action_to_goal(action_id)
                first_action = False

            first_participant = False

    def capture_interactions(self) -> None:
        actions = self.model.nodes_of_type("OperationalActivity")
        if len(actions) < 2:
            return

        for source_id in list(actions):
            source_label = self.model.action_label(source_id)
            if not self.ask_yes_no(
                f"Does '{source_label}' send, provide, request, or transfer anything to another action?",
                "Interactions reveal information, material, requests, or other items that flow through the operation.",
            ):
                continue

            add_more = True
            while add_more:
                item = self.ask_validated(
                    question="What is exchanged?",
                    explanation="Name the information, material, request, or item in a few words.",
                    example="Threat assessment",
                    expected_concept="OperationalExchange",
                    why="Naming what is exchanged makes the operational interaction explicit.",
                    context=f"Source action: {source_label}. {self.model.short_context()}",
                )
                targets = [node_id for node_id in actions if node_id != source_id]
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
                    self.add_notice(f"Could not add the interaction: {error}")

                add_more = self.ask_yes_no(
                    f"Is anything else exchanged from '{source_label}'?",
                    "Add another item only when it is a distinct operational interaction.",
                )

    def capture_communication(self) -> None:
        for source_action, target_action, exchange_name in self.model.exchanges():
            source_participant = self.model.participant_for_activity(source_action)
            target_participant = self.model.participant_for_activity(target_action)
            if not source_participant or not target_participant:
                continue
            if source_participant == target_participant:
                continue
            if self.model.has_communication_between(source_participant, target_participant):
                continue

            source_name = self.model.name(source_participant)
            target_name = self.model.name(target_participant)
            if not self.ask_yes_no(
                f"Do {source_name} and {target_name} use a communication method for '{exchange_name}'?",
                "If the interaction crosses between different participants, the communication method may be important operationally.",
            ):
                continue

            medium = self.ask_validated(
                question="How do they communicate?",
                explanation="Name the real-world communication method, not software or implementation details.",
                example="Voice communication",
                expected_concept="CommunicationMean",
                why="This records how two operational participants are able to interact.",
                context=f"Participants: {source_name} and {target_name}. Interaction: {exchange_name}.",
            )
            ok, error = self.model.add_relation(
                source_participant,
                "COMMUNICATION_MEAN",
                target_participant,
                name=medium,
            )
            if ok:
                self.add_notice(f"Added communication method: {medium}")
            else:
                self.add_notice(f"Could not add the communication method: {error}")

    def run(self) -> None:
        self.capture_goals()
        self.capture_participants_and_actions()
        self.capture_interactions()
        self.capture_communication()

        self.clear_screen()
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
