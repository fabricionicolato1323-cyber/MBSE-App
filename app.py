from __future__ import annotations

import app_base as _base
from app_base import *  # noqa: F401,F403 - preserve the public surface of app.py
from app_extensions import EnhancedOAAppMixin


class OAApp(EnhancedOAAppMixin, _base.OAApp):
    """Current guided builder with focused editing and validation improvements."""


_base.OAApp = OAApp
main = _base.main


if __name__ == "__main__":
    main()
