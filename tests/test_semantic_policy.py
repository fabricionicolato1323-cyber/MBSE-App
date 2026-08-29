import json
import os
import tempfile
from pathlib import Path

from semantic_policy import POLICY_ENV, load_semantic_policy, policy_terms


def test_semantic_policy_can_be_replaced_without_code_changes():
    previous = os.environ.get(POLICY_ENV)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "semantic_policy.json"
            path.write_text(
                json.dumps(
                    {
                        "technical_solution_terms": ["configured-technical-marker"],
                        "plural_markers": ["configured-plural-marker"],
                        "policy": {"allow_scenario_vocabulary": False},
                    }
                ),
                encoding="utf-8",
            )
            os.environ[POLICY_ENV] = str(path)
            load_semantic_policy.cache_clear()

            assert policy_terms("technical_solution_terms") == {
                "configured-technical-marker"
            }
            assert policy_terms("plural_markers") == {"configured-plural-marker"}
            assert not policy_terms("non_english_markers")
    finally:
        if previous is None:
            os.environ.pop(POLICY_ENV, None)
        else:
            os.environ[POLICY_ENV] = previous
        load_semantic_policy.cache_clear()
