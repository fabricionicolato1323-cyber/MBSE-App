from __future__ import annotations


class DirectLoadedModelResumeMixin:
    """Open a loaded model directly at its continuation menu.

    The previous yes/no question about whether to edit was redundant because both
    answers continued to the same loaded-model menu. Mandatory structural gaps are
    still reviewed first. When there is no gap, or after gap review ends, the user
    is taken directly to the available model continuation actions.

    Loaded-model interaction editing also deliberately uses the same explicit
    per-interaction Communication Mean flow as normal refinement. This prevents an
    older loaded-model helper from silently accepting any communication link that
    happens to exist between the performers.
    """

    def _capture_communication_for_exchange(
        self,
        source_action: str,
        target_action: str,
        exchange_name: str,
    ) -> None:
        """Compatibility hook used by the loaded new-action continuation flow."""
        self.capture_communication_for_exchange(
            source_action,
            target_action,
            exchange_name,
        )

    def _run_loaded_refinement_loop(self) -> None:
        """Return to the loaded-model menu after one focused change at a time."""
        while True:
            choice = self._loaded_refinement_menu()

            if choice == "new_goal":
                self._create_loaded_goal()
                continue
            if choice == "new_participant":
                self._create_loaded_participant()
                continue
            if choice == "new_action":
                self._create_new_action_reference()
                continue
            if choice == "participants":
                self.capture_participants_and_actions()
                continue
            if choice == "interactions":
                # FocusedRefinementMixin now handles the selected exchange and its
                # Communication Mean immediately. Do not sweep every interaction
                # afterward or the user would be asked unrelated questions again.
                self.capture_interactions()
                continue
            if choice == "characteristics":
                self.capture_characteristics()
                continue
            if choice == "check":
                self.show_command_page("MODEL CHECK", self._scope_check_text())
                continue
            if choice == "finish":
                print()
                print("Modeling session finished.")
                return

    def run(self) -> None:
        self._mark_loaded_model_as_refinement()
        model_name = str(self.model.graph.graph.get("model_name") or "loaded model")
        self.add_notice(f"Loaded model: {model_name}")

        self._review_loaded_gaps()
        self._run_loaded_refinement_loop()
