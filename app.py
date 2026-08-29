from __future__ import annotations

import app_base as _base
from app_base import *  # noqa: F401,F403 - preserve the public surface of app.py
from characteristic_operators import install_characteristic_operator_support
from characteristics_flow import CharacteristicsFlowMixin
from composition_flow import CompositionFlowMixin
from guidance_flow import GuidanceFlowMixin
from participant_flow import ParticipantFlowMixin


# Extend the central graph characteristic schema before any OAApp instance is
# created. This also affects the web autosave subclass because it inherits from
# the same graph model class.
install_characteristic_operator_support()


class OAApp(
    GuidanceFlowMixin,
    ParticipantFlowMixin,
    CompositionFlowMixin,
    CharacteristicsFlowMixin,
    _base.OAApp,
):
    """Guided builder with neutral UI guidance and Feature 4 refinements."""

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
