from __future__ import annotations

import argparse
import json
from pathlib import Path

import app_base
from action_first_inline_flow import ActionFirstInlineCreationMixin
from action_goal_linking import ActionGoalLinkingMixin
from focused_refinement import FocusedRefinementMixin
from loaded_model_flow import LoadedModelFlowMixin
from model_io import graph_from_model_payload
from web_ai import AIControlManager
from web_guided_flow import WebGuidedFlowMixin
from web_worker import AutosaveOAGraph, WebInteractionMixin, _configure_web_streams


class LoadedAutosaveOAGraph(AutosaveOAGraph):
    def __init__(self, model_path: Path, load_model_path: Path) -> None:
        super().__init__(model_path)
        payload = json.loads(Path(load_model_path).read_text(encoding="utf-8"))
        self.graph = graph_from_model_payload(payload)
        self._history = []
        self._persist()


def main() -> None:
    _configure_web_streams()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--load-model", required=True)
    args = parser.parse_args()

    model_path = Path(args.model_path).resolve()
    load_model_path = Path(args.load_model).resolve()
    app_base.OAGraph = lambda: LoadedAutosaveOAGraph(  # type: ignore[assignment]
        model_path,
        load_model_path,
    )

    import app

    class LoadedWebOAApp(
        WebInteractionMixin,
        ActionFirstInlineCreationMixin,
        ActionGoalLinkingMixin,
        FocusedRefinementMixin,
        LoadedModelFlowMixin,
        WebGuidedFlowMixin,
        app.OAApp,
    ):
        pass

    web_app = LoadedWebOAApp()
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
