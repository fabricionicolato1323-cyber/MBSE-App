from __future__ import annotations


class DirectLoadedModelResumeMixin:
    """Open a loaded model directly at its continuation menu.

    The previous yes/no question about whether to edit was redundant because both
    answers continued to the same loaded-model menu. Mandatory structural gaps are
    still reviewed first. When there is no gap, or after gap review ends, the user
    is taken directly to the available model continuation actions.
    """

    def run(self) -> None:
        self._mark_loaded_model_as_refinement()
        model_name = str(self.model.graph.graph.get("model_name") or "loaded model")
        self.add_notice(f"Loaded model: {model_name}")

        self._review_loaded_gaps()
        self._run_loaded_refinement_loop()
