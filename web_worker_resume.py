from __future__ import annotations

import argparse
import json
from pathlib import Path

import app_base
from action_first_inline_flow import ActionFirstInlineCreationMixin
from action_goal_linking import ActionGoalLinkingMixin
from focused_refinement import FocusedRefinementMixin
from loaded_model_deletion import LoadedModelDeletionMixin
from loaded_model_direct_resume import DirectLoadedModelResumeMixin
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
        LoadedModelDeletionMixin,
        DirectLoadedModelResumeMixin,
        LoadedModelFlowMixin,
        WebGuidedFlowMixin,
        app.OAApp,
    ):
        def _select_node_for_deletion(self, node_type: str, label: str) -> str | None:
            node_ids = self.model.nodes_of_type(node_type)
            if not node_ids:
                self.add_notice(f"No {label} exists yet.")
                return None
            return self.ask_choice(
                f"Which {label} would you like to delete?",
                [(node_id, self.model.name(node_id)) for node_id in node_ids],
                "Choose one item. Nothing will be deleted until you review the impact and confirm.",
            )

        def _delete_loaded_goal(self) -> None:
            node_id = self._select_node_for_deletion("OperationalCapability", "goal")
            if node_id:
                self._delete_selected_node(node_id)

        def _delete_loaded_activity(self) -> None:
            node_id = self._select_node_for_deletion("OperationalActivity", "activity")
            if node_id:
                self._delete_selected_node(node_id)

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
