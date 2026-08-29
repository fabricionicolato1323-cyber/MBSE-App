from __future__ import annotations

from app_base import DEFAULT_SAVE_PATH
from current_scope import compare_current_scope, format_current_scope_comparison
from presentation import friendly_model_view
from terminal_ui import processing_indicator


_REVIEW_HELP = """Commands:
  /help       Show commands
  /ask QUESTION
              Ask a method question using the available guidance
  /compare    Check the model against the currently implemented rules
  /show       Show the complete model in user-facing terms
  /check      Check for obvious gaps and structural inconsistencies
  /save       Save without finishing
  /undo       Undo the last accepted model change
  /clc        Clear the terminal screen
  /done       Validate, save, and finish
  /quit       Exit without declaring the model complete

After the guided questions, the model stays open for review.
Only /done declares the current model finished.
""".strip()


class ReviewWorkflowMixin:
    """Keep the model open after elicitation and require explicit finalization."""

    def command(self, value: str) -> bool:
        raw = value.strip()
        cmd = raw.casefold()

        if cmd == "/help":
            self.show_command_page("HELP", _REVIEW_HELP)
            return True

        if cmd == "/show":
            self.show_command_page("MODEL SO FAR", friendly_model_view(self.model))
            return True

        if cmd == "/done":
            with processing_indicator("Checking model consistency"):
                comparison = compare_current_scope(self.knowledge, self.model)

            if not comparison.conforms:
                self.show_command_page(
                    "MODEL NOT READY TO FINISH",
                    format_current_scope_comparison(comparison),
                )
                self.add_notice(
                    "Resolve the mandatory inconsistencies before finishing. "
                    "The model remains open for review."
                )
                return True

            path = self.model.save(str(DEFAULT_SAVE_PATH))
            print()
            print("=" * 72)
            print("MODEL FINALIZED")
            print("=" * 72)
            print(format_current_scope_comparison(comparison, max_issues=8))
            print(f"\nSaved: {path}")
            print("Finished.")
            raise SystemExit(0)

        return super().command(value)

    def run(self) -> None:
        print()
        print("The app provides guidance and deterministic validation checks.")
        print("You remain responsible for confirming the quality of the final model.")

        goals = self.capture_goals()
        self.capture_goal_candidates(goals)
        self.capture_participants_and_actions()
        self.capture_structure_and_environment()
        self.capture_interactions()
        self.capture_communication()

        self.add_notice(
            "Guided questions are complete. The model remains open for review. "
            "Use /show, /check, and /compare before /done."
        )

        while True:
            self.current_why = (
                "Review keeps the model editable and inspectable before you "
                "explicitly declare it finished."
            )
            self.draw_question(
                "Review the model before finishing.",
                explanation=(
                    "Use /show, /check, /compare, /undo, /save, or /done. "
                    "Use /quit to exit without declaring the model complete."
                ),
                expected_structure="Command",
            )
            value = input("> ").strip()
            if self.command(value):
                continue
            self.add_notice(
                "The guided questions are complete. Use one of the review commands shown above."
            )
