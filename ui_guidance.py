from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


DEFAULT_GUIDANCE_PATH = Path(__file__).with_name("ui_guidance.json")
GUIDANCE_ENV = "MBSE_UI_GUIDANCE_PATH"


def _read_guidance(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


@lru_cache(maxsize=1)
def load_ui_guidance() -> dict:
    """Load neutral UI guidance from a configurable external JSON file.

    Runtime Python does not own domain examples or user-facing refinement labels.
    If a custom guidance file is supplied through MBSE_UI_GUIDANCE_PATH, it
    replaces the repository default for configured values. Missing or malformed
    files fail closed for optional guidance.
    """
    configured = os.getenv(GUIDANCE_ENV, "").strip()
    path = Path(configured).expanduser() if configured else DEFAULT_GUIDANCE_PATH
    return _read_guidance(path)


@lru_cache(maxsize=1)
def _default_ui_guidance() -> dict:
    """Read repository defaults for required interaction vocabulary fallbacks."""
    return _read_guidance(DEFAULT_GUIDANCE_PATH)


def configured_example(expected_structure: str) -> str:
    """Return the configured neutral example for an answer structure."""
    data = load_ui_guidance()
    examples = data.get("examples_by_expected_structure", {})
    if not isinstance(examples, dict):
        return ""
    value = examples.get(expected_structure, "")
    return str(value).strip() if value is not None else ""


def configured_section(name: str) -> dict:
    """Return one configured UI section, falling back to repository defaults.

    This keeps user-facing vocabulary outside the model/refinement Python logic
    while allowing deployments to replace the wording through the existing
    MBSE_UI_GUIDANCE_PATH configuration mechanism.
    """
    key = str(name or "").strip()
    if not key:
        return {}

    configured = load_ui_guidance().get(key)
    if isinstance(configured, dict):
        return configured

    fallback = _default_ui_guidance().get(key)
    return fallback if isinstance(fallback, dict) else {}


def configured_text(section: str, key: str) -> str:
    """Return a configured text value without embedding wording in Python."""
    value = configured_section(section).get(key, "")
    return str(value).strip() if value is not None else ""


def configured_choices(section: str, key: str) -> list[tuple[str, str]]:
    """Return configured stable IDs paired with their display labels."""
    raw = configured_section(section).get(key, [])
    if not isinstance(raw, list):
        return []

    choices: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        choice_id = str(item.get("id", "")).strip()
        label = str(item.get("label", "")).strip()
        if choice_id and label:
            choices.append((choice_id, label))
    return choices


def literal_domain_examples_allowed() -> bool:
    data = load_ui_guidance()
    policy = data.get("policy", {})
    return bool(policy.get("allow_literal_domain_examples", False)) if isinstance(policy, dict) else False
