import json
import os
import tempfile
from pathlib import Path

from semantic_policy import POLICY_ENV, load_semantic_policy, policy_terms


def main() -> None:
    assert policy_terms("goal_outcome_verbs")
    assert policy_terms("technical_solution_terms")
    assert policy_terms("plural_markers")

    previous = os.environ.get(POLICY_ENV)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "semantic_policy.json"
        path.write_text(
            json.dumps(
                {
                    "goal_outcome_verbs": ["configuredverb"],
                    "technical_solution_terms": ["configured-technical-marker"],
                    "plural_markers": ["configured-plural-marker"],
                    "policy": {"allow_scenario_vocabulary": False},
                }
            ),
            encoding="utf-8",
        )
        os.environ[POLICY_ENV] = str(path)
        load_semantic_policy.cache_clear()

        assert policy_terms("goal_outcome_verbs") == {"configuredverb"}
        assert policy_terms("technical_solution_terms") == {
            "configured-technical-marker"
        }
        assert policy_terms("plural_markers") == {"configured-plural-marker"}
        assert not policy_terms("non_english_markers")

    if previous is None:
        os.environ.pop(POLICY_ENV, None)
    else:
        os.environ[POLICY_ENV] = previous
    load_semantic_policy.cache_clear()

    print("Semantic policy test passed.")


if __name__ == "__main__":
    main()
