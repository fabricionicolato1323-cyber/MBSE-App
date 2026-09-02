from __future__ import annotations

import json
from typing import Any

INTERACTION_PREFIX = "__MBSE_WEB_INTERACTION__ "
VALID_INTERACTION_MODES = {"free_text", "yes_no", "choice", "continue"}


def normalize_interaction(payload: Any) -> dict[str, Any]:
    """Return a safe browser interaction payload.

    The worker emits this structured contract before it waits for terminal input.
    The browser therefore does not need to infer controls from human-readable
    prompt text.
    """
    if not isinstance(payload, dict):
        return {"mode": "free_text", "choices": []}

    mode = str(payload.get("mode", "free_text")).strip().casefold()
    if mode not in VALID_INTERACTION_MODES:
        mode = "free_text"

    choices: list[dict[str, str]] = []
    raw_choices = payload.get("choices", [])
    if isinstance(raw_choices, list):
        for item in raw_choices:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            value = str(item.get("value", ""))
            if label:
                choices.append({"label": label, "value": value})

    if mode == "yes_no" and not choices:
        choices = [
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"},
        ]
    elif mode == "continue" and not choices:
        choices = [{"label": "Continue", "value": ""}]

    return {"mode": mode, "choices": choices}


def encode_interaction(payload: dict[str, Any]) -> str:
    normalized = normalize_interaction(payload)
    return INTERACTION_PREFIX + json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def decode_latest_interaction(raw: str) -> dict[str, Any] | None:
    """Decode the newest explicit interaction marker from worker output."""
    for line in reversed(raw.replace("\r", "").splitlines()):
        stripped = line.strip()
        if not stripped.startswith(INTERACTION_PREFIX):
            continue
        encoded = stripped[len(INTERACTION_PREFIX):]
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            return None
        return normalize_interaction(payload)
    return None


def is_interaction_protocol_line(line: str) -> bool:
    return line.strip().startswith(INTERACTION_PREFIX)
