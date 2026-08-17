from __future__ import annotations

import itertools
import sys
import threading
from contextlib import contextmanager
from typing import Iterator


EXPECTED_STRUCTURES = {
    "yes_no": "yes / no",
    "number": "one number from the list",
    "participant": (
        "noun phrase — person, role, group, organization, place, resource, or context"
    ),
    "OperationalCapability": (
        "verb + desired state/object [+ optional complement]"
    ),
    "OperationalActivity": (
        "subject(s) optional + verb(s) + object(s)/complement(s); "
        "multiple actions are allowed in one natural sentence"
    ),
    "OperationalExchange": (
        "noun phrase — information, material, request, or exchanged item"
    ),
    "CommunicationMean": (
        "noun phrase — real-world communication method"
    ),
}


@contextmanager
def processing_indicator(
    message: str = "Processing with local AI",
) -> Iterator[None]:
    """Show animated dots while a blocking local-AI call runs.

    Uses only carriage returns and ASCII so it works reliably in Windows
    PowerShell, cmd.exe, VS Code terminals, and typical Unix terminals.
    It never clears terminal history.
    """
    if not sys.stdout.isatty():
        print(f"{message}...")
        yield
        return

    stop_event = threading.Event()
    frames = itertools.cycle(("", ".", "..", "..."))
    prefix = message
    line_width = max(40, len(prefix) + 6)

    def animate() -> None:
        while not stop_event.is_set():
            dots = next(frames)
            sys.stdout.write(
                "\r" + f"{prefix}{dots}".ljust(line_width)
            )
            sys.stdout.flush()
            if stop_event.wait(0.35):
                break

    thread = threading.Thread(
        target=animate,
        name="local-ai-progress",
        daemon=True,
    )
    thread.start()

    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=1.0)
        sys.stdout.write("\r" + (" " * line_width) + "\r")
        sys.stdout.flush()
