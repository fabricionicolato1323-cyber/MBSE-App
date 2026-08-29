from __future__ import annotations

from app_base import OAApp as BaseOAApp


class LoadedModelFlowMixin:
    """Resume a saved model by reviewing mandatory gaps before normal refinement."""

    def _mark_loaded_model_as_refinement(self) -> None:
        self._focused_participant_initial_pass_done = True
        self._focused_interaction_initial_pass_done = True

    def _first_loaded_gap(self) -> dict | None:
        goals = self.model.nodes_of_type("OperationalCapability")
        participants = self.model.participants()
        actions = self.model.nodes_of_type("OperationalActivity")

        if not goals:
            return {
                "kind": "goal",
                "message": "The loaded model has no operational goal.",
            }
        if not participants:
            return {
                "kind": "participant",
                "message": "The loaded model has no participant or context element.",
            }

        for participant_id in self.model.active_participants():
            if not self.model.actions_for_participant(participant_id):
                return {
                    "kind": "participant_action",
                    "participant_id": participant_id,
                    "message": (
                        f"'{self.model.name(participant_id)}' is an active participant "
                        "but has no action."
                    ),
                }

        if not actions:
            return {
                "kind": "new_action",
                "message": "The loaded model has no operational action.",
            }

        for action_id in actions:
            if not self.model.participants_for_activity(action_id):
                return {
                    "kind": "action_performer",
                    "action_id": action_id,
                    "message": f"'{self.model.name(action_id)}' has no confirmed performer.",
                }

        for action_id in actions:
            linked = any(
                data.get("type") == "SUPPORTS_CAPABILITY"
                for _, _, data in self.model.graph.out_edges(action_id, data=True)
            )
            if not linked:
                return {
                    "kind": "action_goal",
                    "action_id": action_id,
                    "message": f"'{self.model.name(action_id)}' is not connected to a goal.",
                }
        return None

    def _assign_loaded_action_performer(self, action_id: str) -> None:
        candidates = self.model.active_participants()
        choices = [
            (participant_id, self._participant_refinement_label(participant_id))
            for participant_id in candidates
        ]
        choices.append(("__new_participant__", "+ Add new participant / context"))
        selected = self.ask_choice(
            f"Who performs '{self.model.name(action_id)}'?",
            choices,
            "A loaded action needs at least one confirmed operational performer.",
        )
        if selected == "__new_participant__":
            selected = self._capture_one_participant()
        if not selected:
            return
        if not self.model.expects_activity(selected):
            self.add_notice("That item is context only and cannot perform an action.")
            return
        ok, error = self.model.add_relation(selected, "PERFORMS", action_id)
        if not ok:
            self.add_notice(f"Could not assign the performer: {error}")

    def _address_loaded_gap(self, gap: dict) -> None:
        kind = gap.get("kind")
        if kind == "goal":
            self.capture_goals()
            return
        if kind == "participant":
            participant_id = self._capture_one_participant()
            if participant_id is not None and self.model.expects_activity(participant_id):
                self.capture_actions_for_participant(participant_id)
            return
        if kind == "participant_action":
            self.capture_actions_for_participant(gap["participant_id"])
            return
        if kind == "new_action":
            self._create_new_action_reference()
            return
        if kind == "action_performer":
            self._assign_loaded_action_performer(gap["action_id"])
            return
        if kind == "action_goal":
            self.link_action_to_goal(gap["action_id"])

    def _review_loaded_gaps(self) -> bool:
        reviewed_any = False
        while True:
            gap = self._first_loaded_gap()
            if gap is None:
                return reviewed_any
            if not self.ask_yes_no(
                f"{gap['message']} Would you like to address this now?",
                "The app uses the saved model itself to resume at the first clear mandatory gap.",
            ):
                return reviewed_any
            reviewed_any = True
            self._address_loaded_gap(gap)

    def _run_loaded_refinement_loop(self) -> None:
        while True:
            choice = self._refinement_menu()

            if choice == "participants":
                self.capture_participants_and_actions()
                continue
            if choice == "interactions":
                self.capture_interactions()
                BaseOAApp.capture_communication(self)
                continue
            if choice == "characteristics":
                self.capture_characteristics()
                continue
            if choice == "check":
                self.show_command_page("MODEL CHECK", self._scope_check_text())
                continue
            if choice == "save":
                self.add_notice("Model export completed. You can continue editing.")
                continue
            if choice == "finish":
                print()
                print("Modeling session finished.")
                return

    def run(self) -> None:
        self._mark_loaded_model_as_refinement()
        model_name = str(self.model.graph.graph.get("model_name") or "loaded model")
        self.add_notice(f"Loaded model: {model_name}")

        reviewed_any = self._review_loaded_gaps()
        if not reviewed_any and self._first_loaded_gap() is None:
            wants_edit = self.ask_yes_no(
                "The loaded model has no obvious mandatory gaps. Would you like to edit or refine something?",
                "You can refine existing content, add information, check the model, save it again, or finish.",
            )
            if not wants_edit:
                self.add_notice(
                    "No edit selected. Use the next-step menu to check, save, or finish the model."
                )
        self._run_loaded_refinement_loop()
