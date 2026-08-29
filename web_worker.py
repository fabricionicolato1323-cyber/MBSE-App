from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import sys
from typing import Callable, Iterator

import app_base
from action_first_inline_flow import ActionFirstInlineCreationMixin
from action_goal_linking import ActionGoalLinkingMixin
from graph_model import OAGraph
from web_ai import AIControlManager
from web_guided_flow import WebGuidedFlowMixin
from web_protocol import encode_interaction, normalize_interaction


def _configure_web_streams() -> None:
    """Use UTF-8 explicitly for the browser/worker subprocess protocol.

    Windows console code pages do not necessarily represent symbols such as ≥
    and ≤.  The web bridge uses UTF-8 pipes, so configure the child process to
    use the same encoding instead of inheriting the console locale.
    """
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(
                encoding="utf-8",
                errors="replace" if stream_name == "stdin" else "backslashreplace",
            )
        except (OSError, ValueError):
            pass


class AutosaveOAGraph(OAGraph):
    """OAGraph variant that mirrors accepted changes for the web preview."""

    def __init__(self, model_path: Path) -> None:
        super().__init__()
        self._web_model_path = Path(model_path)
        self._persist()

    def _persist(self) -> None:
        self.save(str(self._web_model_path))

    def add_node(self, *args, **kwargs):
        result = super().add_node(*args, **kwargs)
        if result[0]:
            self._persist()
        return result

    def update_node_attributes(self, *args, **kwargs):
        result = super().update_node_attributes(*args, **kwargs)
        if result:
            self._persist()
        return result

    def add_relation(self, *args, **kwargs):
        result = super().add_relation(*args, **kwargs)
        if result[0]:
            self._persist()
        return result

    def add_characteristic(self, *args, **kwargs):
        result = super().add_characteristic(*args, **kwargs)
        if result[0]:
            self._persist()
        return result

    def add_exchange_characteristic(self, *args, **kwargs):
        result = super().add_exchange_characteristic(*args, **kwargs)
        if result[0]:
            self._persist()
        return result

    def undo(self) -> bool:
        changed = super().undo()
        if changed:
            self._persist()
        return changed


class WebInteractionMixin:
    """Publish explicit browser input controls without changing model logic."""

    _web_interaction_override: dict | None = None

    @staticmethod
    def _friendly_question(question: str) -> str:
        replacements = (
            ("What kind of Operational Entity is it?", "What kind of participant or context element is it?"),
            ("Operational Entity", "participant / context"),
            ("Operational Actor", "person / role"),
        )
        result = question
        for old, new in replacements:
            result = result.replace(old, new)
        return result

    @staticmethod
    def _friendly_choice_label(label: str) -> str:
        labels = {
            "Classify as Operational Actor": "Person / role",
            "Classify as Operational Entity": "Organization, group, facility or other participant",
            "Confirm the suggestion": "Use suggested classification",
            "Ask Ollama for another opinion": "Ask AI for another opinion",
        }
        return labels.get(label, label)

    @staticmethod
    def _friendly_extra_lines(extra_lines: list[str] | None) -> list[str] | None:
        if not extra_lines:
            return extra_lines

        hidden_prefixes = (
            "Suggestion:",
            "Nature:",
            "Evidence:",
            "Reason:",
            "The suggestion is advisory",
        )
        result: list[str] = []
        for line in extra_lines:
            stripped = line.strip()
            if stripped.startswith(hidden_prefixes):
                continue
            result.append(line)
        return result

    def _visible_choices_for_ai_state(
        self,
        choices: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        """Hide AI/suggestion affordances that are not available in the current state."""
        if getattr(self, "llm", None) is not None:
            return list(choices)
        return [
            (key, label)
            for key, label in choices
            if label != "Confirm the suggestion"
            and label != "Ask Ollama for another opinion"
        ]

    def _emit_web_interaction(self, payload: dict) -> None:
        print(encode_interaction(payload), flush=True)

    @contextmanager
    def _web_interaction_scope(self, payload: dict) -> Iterator[None]:
        previous = self._web_interaction_override
        self._web_interaction_override = normalize_interaction(payload)
        try:
            yield
        finally:
            self._web_interaction_override = previous

    def draw_question(
        self,
        question: str,
        explanation: str = "",
        example: str = "",
        expected_structure: str = "",
        extra_lines: list[str] | None = None,
    ) -> None:
        interaction = self._web_interaction_override or {
            "mode": "free_text",
            "choices": [],
        }
        interaction = normalize_interaction(interaction)
        self._emit_web_interaction(interaction)

        if interaction["mode"] == "choice":
            if explanation.strip().casefold().startswith("choose one of the numbers"):
                explanation = "Select one of the options below."
            if expected_structure.strip().casefold() in {
                "one number from the list",
                "number",
            }:
                expected_structure = "Select one option"
        elif interaction["mode"] == "yes_no":
            expected_structure = ""
        elif interaction["mode"] == "continue":
            expected_structure = ""

        return super().draw_question(
            self._friendly_question(question),
            explanation=explanation,
            example=example,
            expected_structure=expected_structure,
            extra_lines=self._friendly_extra_lines(extra_lines),
        )

    def ask_yes_no(self, question: str, why: str) -> bool:
        interaction = {
            "mode": "yes_no",
            "choices": [
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        }
        with self._web_interaction_scope(interaction):
            return super().ask_yes_no(self._friendly_question(question), why)

    def ask_number(
        self,
        question: str,
        node_ids: list[str],
        label: Callable[[str], str],
        why: str,
    ) -> str:
        interaction = {
            "mode": "choice",
            "choices": [
                {"label": label(node_id), "value": str(index)}
                for index, node_id in enumerate(node_ids, start=1)
            ],
        }
        with self._web_interaction_scope(interaction):
            return super().ask_number(
                self._friendly_question(question),
                node_ids,
                label,
                why,
            )

    def ask_choice(
        self,
        question: str,
        choices: list[tuple[str, str]],
        why: str,
        extra_lines: list[str] | None = None,
    ) -> str:
        visible_choices = self._visible_choices_for_ai_state(choices)
        display_choices = [
            (key, self._friendly_choice_label(label))
            for key, label in visible_choices
        ]
        interaction = {
            "mode": "choice",
            "choices": [
                {"label": label, "value": str(index)}
                for index, (_, label) in enumerate(display_choices, start=1)
            ],
        }
        with self._web_interaction_scope(interaction):
            return super().ask_choice(
                self._friendly_question(question),
                display_choices,
                why,
                extra_lines=self._friendly_extra_lines(extra_lines),
            )

    def pause(self) -> None:
        self._emit_web_interaction(
            {
                "mode": "continue",
                "choices": [{"label": "Continue", "value": ""}],
            }
        )
        input("\nPress Enter to return to the current question...")


def main() -> None:
    _configure_web_streams()

    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    args = parser.parse_args()
    model_path = Path(args.model_path).resolve()

    app_base.OAGraph = lambda: AutosaveOAGraph(model_path)  # type: ignore[assignment]

    import app

    class WebOAApp(
        WebInteractionMixin,
        ActionFirstInlineCreationMixin,
        ActionGoalLinkingMixin,
        WebGuidedFlowMixin,
        app.OAApp,
    ):
        pass

    web_app = WebOAApp()

    web_app.llm = None
    web_app.notice = ""
    ai_controller = AIControlManager(web_app, model_path.parent)
    ai_controller.start()
    try:
        web_app.run()
    finally:
        ai_controller.stop()


if __name__ == "__main__":
    main()
