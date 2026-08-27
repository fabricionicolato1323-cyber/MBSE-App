from __future__ import annotations

import app_base as _base
from app_base import *  # noqa: F401,F403 - preserve the public surface of app.py
from app_extensions import EnhancedOAAppMixin


class OAApp(EnhancedOAAppMixin, _base.OAApp):
    """Current guided builder with focused editing and validation improvements."""

    @staticmethod
    def _sync_runtime_config() -> None:
        """Keep public app configuration effective inside inherited base methods."""
        _base.DEFAULT_SAVE_PATH = DEFAULT_SAVE_PATH

    def command(self, raw: str) -> bool:
        self._sync_runtime_config()
        return super().command(raw)

    def run(self) -> None:
        self._sync_runtime_config()
        return super().run()


_base.OAApp = OAApp
main = _base.main


if __name__ == "__main__":
    main()
