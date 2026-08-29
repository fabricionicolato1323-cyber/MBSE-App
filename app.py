from __future__ import annotations

import app_base as _base
from app_base import *  # noqa: F401,F403 - preserve the public surface of app.py
from characteristics_flow import CharacteristicsFlowMixin
from composition_flow import CompositionFlowMixin
from consistency_flow import ConsistencyFlowMixin
from guidance_flow import GuidanceFlowMixin
from participant_flow import ParticipantFlowMixin
from review_flow import ReviewWorkflowMixin
from user_experience import UserExperienceMixin


class OAApp(
    ReviewWorkflowMixin,
    UserExperienceMixin,
    ConsistencyFlowMixin,
    GuidanceFlowMixin,
    ParticipantFlowMixin,
    CompositionFlowMixin,
    CharacteristicsFlowMixin,
    _base.OAApp,
):
    """Guided builder with explicit review, simplified UI, and integrated consistency."""

    def capture_structure_and_environment(self) -> None:
        super().capture_structure_and_environment()
        self.capture_decomposition()

    def capture_communication(self) -> None:
        super().capture_communication()
        self.capture_characteristics()


# app_base.main resolves OAApp from its own module globals. Rebinding preserves
# the established entry point while making it instantiate the extended class.
_base.OAApp = OAApp
main = _base.main


if __name__ == "__main__":
    main()
