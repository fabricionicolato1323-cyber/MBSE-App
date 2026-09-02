from __future__ import annotations

from app_base import DEFAULT_SAVE_PATH, OAApp as BaseOAApp
from next_best_question import NextBestQuestion, best_next_question
from web_guided_flow import WebGuidedFlowMixin


_OPTIONAL_REVIEW_KEYS = {"review_interactions", "review_characteristics"}


def _ignored_recommendations(self) -> set[str]:
    ignored = getattr(self, "_nbq_ignored_identities", None)
    if ignored is None:
        ignored = set()
        self._nbq_ignored_identities = ignored
    return ignored


def _current_recommendation(self) -> NextBestQuestion | None:
    return best_next_question(
        self.model,
        ignored_identities=_ignored_recommendations(self),
    )


def _manual_refinement_menu(self) -> str:
    return self.ask_choice(
        "What would you like to do next?",
        [
            ("participants", "Add or refine participants and actions"),
            ("interactions", "Add or refine interactions"),
            ("characteristics", "Add or refine characteristics"),
            ("check", "Check model"),
            ("save", "Save"),
            ("finish", "Finish modeling"),
        ],
        "Choose the area you want to work on.",
    )


def _adaptive_refinement_menu(self) -> str:
    recommendation = _current_recommendation(self)
    self._nbq_pending_recommendation = recommendation
    if recommendation is None:
        return _manual_refinement_menu(self)

    return self.ask_choice(
        "What would you like to do next?",
        [
            ("recommended", f"Recommended: {recommendation.action_label}"),
            ("other", "Choose another task"),
            ("check", "Check model"),
            ("save", "Save"),
            ("finish", "Finish modeling"),
        ],
        "The first option is selected from the current model state. Nothing is changed until you answer the next question.",
    )


def _add_missing_goal(self) -> None:
    goal = self.ask_validated(
        question="What is the main goal?",
        explanation="Describe the desired outcome in one short sentence.",
        expected_concept="OperationalCapability",
        why="A goal gives the remaining model a clear outcome to support.",
    )
    self.add_node("OperationalCapability", goal)


def _add_missing_participant(self) -> None:
    self._capture_one_participant()


def _capture_missing_participant_action(self, participant_id: str | None) -> None:
    if not participant_id or participant_id not in self.model.graph:
        return
    self.capture_actions_for_participant(participant_id)


def _assign_missing_action_performer(self, action_id: str | None) -> None:
    if not action_id or action_id not in self.model.graph:
        return
    performer_id = self._select_action_performer()
    if not performer_id:
        return
    ok, error = self.model.add_relation(performer_id, "PERFORMS", action_id)
    if ok:
        self.add_notice(
            f"Assigned '{self.model.name(action_id)}' to {self.model.name(performer_id)}."
        )
    else:
        self.add_notice(f"Could not assign the action: {error}")


def _connect_missing_action_goal(self, action_id: str | None) -> None:
    if not action_id or action_id not in self.model.graph:
        return
    self.link_action_to_goal(action_id)


def _capture_missing_communication(
    self,
    source_participant: str | None,
    target_participant: str | None,
) -> None:
    if not source_participant or not target_participant:
        return
    if source_participant not in self.model.graph or target_participant not in self.model.graph:
        return
    if self.model.has_communication_between(source_participant, target_participant):
        return

    source_name = self.model.name(source_participant)
    target_name = self.model.name(target_participant)
    mean = self.ask_validated(
        question=f"How do {source_name} and {target_name} communicate?",
        explanation="Name the real-world communication method.",
        expected_concept="CommunicationMean",
        why="An existing interaction crosses these participant boundaries.",
    )
    ok, error = self.model.add_relation(
        source_participant,
        "COMMUNICATION_MEAN",
        target_participant,
        name=mean,
    )
    if ok:
        self.add_notice(f"Added communication method: {mean}")
    else:
        self.add_notice(f"Could not add the communication method: {error}")


def _execute_recommendation(self, recommendation: NextBestQuestion) -> None:
    key = recommendation.key

    if key == "missing_goal":
        _add_missing_goal(self)
        return
    if key == "missing_participant":
        _add_missing_participant(self)
        return
    if key == "participant_without_action":
        _capture_missing_participant_action(self, recommendation.target_id)
        return
    if key == "action_without_performer":
        _assign_missing_action_performer(self, recommendation.target_id)
        return
    if key == "action_without_goal":
        _connect_missing_action_goal(self, recommendation.target_id)
        return
    if key == "missing_communication":
        _capture_missing_communication(
            self,
            recommendation.target_id,
            recommendation.secondary_id,
        )
        return
    if key == "review_interactions":
        self.capture_interactions()
    elif key == "review_characteristics":
        self.capture_characteristics()
    else:
        return

    if key in _OPTIONAL_REVIEW_KEYS:
        _ignored_recommendations(self).add(recommendation.identity)


def _adaptive_run(self) -> None:
    print()
    print("The app provides advisory classifications and validation checks.")
    print("You remain responsible for confirming persistent model content.")

    goals = self.capture_goals()
    self.capture_goal_candidates(goals)
    self.capture_participants_and_actions()
    self.capture_structure_and_environment()
    self.capture_interactions()
    self.capture_communication()

    self.add_notice(
        "Initial guided pass complete. The app will now recommend the next useful question from the current model state."
    )

    while True:
        choice = _adaptive_refinement_menu(self)

        if choice == "recommended":
            recommendation = getattr(self, "_nbq_pending_recommendation", None)
            if recommendation is not None:
                _execute_recommendation(self, recommendation)
            continue

        if choice == "other":
            choice = _manual_refinement_menu(self)

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
            self.model.save(str(DEFAULT_SAVE_PATH))
            self.add_notice("Model saved.")
            continue

        if choice == "finish":
            self.model.save(str(DEFAULT_SAVE_PATH))
            print()
            print("Model saved.")
            print("Modeling session finished.")
            return


def install_next_best_question_support() -> None:
    """Install the adaptive refinement loop without changing terminal behavior."""
    if getattr(WebGuidedFlowMixin, "_next_best_question_v1_installed", False):
        return

    WebGuidedFlowMixin._manual_refinement_menu = _manual_refinement_menu
    WebGuidedFlowMixin._refinement_menu = _adaptive_refinement_menu
    WebGuidedFlowMixin._execute_next_best_question = _execute_recommendation
    WebGuidedFlowMixin.run = _adaptive_run
    WebGuidedFlowMixin._next_best_question_v1_installed = True
