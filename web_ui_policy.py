from __future__ import annotations

from typing import Any

from web_protocol import decode_latest_interaction, normalize_interaction


def interaction_from_prompt_delta(delta: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    """Use only the interaction marker belonging to the current prompt delta.

    This prevents an older free-text/choice marker from controlling a newer
    question and avoids the stale-control behavior seen during manual testing.
    """
    explicit = decode_latest_interaction(delta)
    if explicit is not None:
        return explicit
    return normalize_interaction(fallback or {"mode": "free_text"})


def should_track_temporary_input(value: str, interaction: dict[str, Any] | None) -> bool:
    """Only open-ended model content may appear as a temporary model candidate."""
    text = str(value or "").strip()
    mode = normalize_interaction(interaction or {})["mode"]
    return bool(text) and not text.startswith("/") and mode == "free_text"
