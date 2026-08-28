from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


DEFAULT_GUIDANCE_PATH = Path(__file__).with_name("ui_guidance.json")
GUIDANCE_ENV = "MBSE_UI_GUIDANCE_PATH"


@lru_cache(maxsize=1)
def load_ui_guidance() -> dict:
    """Load neutral UI guidance from a configurable external JSON file.

    Runtime Python does not own domain examples. If a custom guidance file is
    supplied through MBSE_UI_GUIDANCE_PATH, it replaces the repository default.
    Missing or malformed files fail closed: the UI simply shows no example.
    """
    configured = os.getenv(GUIDANCE_ENV, "").strip()
    path = Path(configured).expanduser() if configured else DEFAULT_GUIDANCE_PATH

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def configured_example(expected_structure: str) -> str:
    """Return the configured neutral example for an answer structure."""
    data = load_ui_guidance()
    examples = data.get("examples_by_expected_structure", {})
    if not isinstance(examples, dict):
        return ""
    value = examples.get(expected_structure, "")
    return str(value).strip() if value is not None else ""


def literal_domain_examples_allowed() -> bool:
    data = load_ui_guidance()
    policy = data.get("policy", {})
    return bool(policy.get("allow_literal_domain_examples", False)) if isinstance(policy, dict) else False
