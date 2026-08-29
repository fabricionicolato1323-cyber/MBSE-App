from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

import app_base
from graph_model import OAGraph
from web_protocol import encode_interaction, normalize_interaction


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
        self._emit_web_interaction(interaction)
        return super().draw_question(
            question,
            explanation=explanation,
            example=example,
            expected_structure=expected_structure,
            extra_lines=extra_lines,
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
            return super().ask_yes_no(question, why)

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
            return super().ask_number(question, node_ids, label, why)

    def ask_choice(
        self,
        question: str,
        choices: list[tuple[str, str]],
        why: str,
        extra_lines: list[str] | None = None,
    ) -> str:
        interaction = {
            "mode": "choice",
            "choices": [
                {"label": label, "value": str(index)}
                for index, (_, label) in enumerate(choices, start=1)
            ],
        }
        with self._web_interaction_scope(interaction):
            return super().ask_choice(
                question,
                choices,
                why,
                extra_lines=extra_lines,
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    args = parser.parse_args()
    model_path = Path(args.model_path).resolve()

    # app_base creates the graph in OAApp.__init__. Rebinding the factory keeps
    # every existing flow and validation rule while adding live persistence.
    app_base.OAGraph = lambda: AutosaveOAGraph(model_path)  # type: ignore[assignment]

    import app

    class WebOAApp(WebInteractionMixin, app.OAApp):
        pass

    WebOAApp().run()


if __name__ == "__main__":
    main()
