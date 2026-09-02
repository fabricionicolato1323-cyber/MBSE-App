from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


DEFAULT_POLICY_PATH = Path(__file__).with_name("semantic_policy.json")
POLICY_ENV = "MBSE_SEMANTIC_POLICY_PATH"


@lru_cache(maxsize=1)
def load_semantic_policy() -> dict:
    """Load replaceable, domain-neutral semantic heuristics.

    Python code owns algorithms and ontology rules. Vocabulary used by those
    heuristics lives in JSON so it can be reviewed, replaced, or disabled
    without changing runtime code.
    """
    configured = os.getenv(POLICY_ENV, "").strip()
    path = Path(configured).expanduser() if configured else DEFAULT_POLICY_PATH

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def policy_terms(name: str) -> set[str]:
    """Return one normalized term set from the configured semantic policy."""
    raw = load_semantic_policy().get(name, [])
    if not isinstance(raw, list):
        return set()
    return {
        str(value).casefold().strip()
        for value in raw
        if str(value).strip()
    }
