from __future__ import annotations

import app_base as _base
from app_base import *  # noqa: F401,F403 - preserve the public surface of app.py
from characteristics_flow import CharacteristicsFlowMixin


class OAApp(CharacteristicsFlowMixin, _base.OAApp):
    """Existing guided builder plus optional structured characteristics."""

    def capture_communication(self) -> None:
        super().capture_communication()
        self.capture_characteristics()


# app_base.main resolves OAApp from its own module globals. Rebinding preserves
# the established entry point while making it instantiate the extended class.
_base.OAApp = OAApp
main = _base.main


if __name__ == "__main__":
    main()
