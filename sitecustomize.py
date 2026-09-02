"""Runtime stream safety for the local Windows web/terminal processes.

Python imports ``sitecustomize`` automatically during normal interpreter startup
when this repository is on ``sys.path``.  Keep the platform's chosen encoding,
but make writes resilient when a console code page cannot represent a UI symbol
such as >=/<= glyphs used by the guided characteristic flow.
"""

from __future__ import annotations

import sys


def _use_safe_output_errors() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            # Preserve the existing encoding so the parent process can decode the
            # pipe consistently. Non-representable characters become Python-style
            # Unicode escapes instead of terminating the worker.
            reconfigure(errors="backslashreplace")
        except (OSError, ValueError):
            pass


_use_safe_output_errors()
