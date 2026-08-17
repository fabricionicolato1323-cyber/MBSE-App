from candidate_discovery import extract_goal_candidates, filter_goal_candidates


class FakeLLM:
    """Simulates a compact model that merges two valid generic candidates."""

    def _json_chat(self, messages, schema):
        return {
            "candidates": [
                {
                    "mention": "staff and facilities",
                    "candidate_concept": "OperationalEntity",
                    "reason": "Two real-world elements were merged by the model.",
                }
            ]
        }

    def validate_participant(self, candidate, context=""):
        normalized = candidate.strip().casefold()
        if normalized == "staff":
            concept = "OperationalActor"
            valid = True
        elif normalized == "facilities":
            concept = "OperationalEntity"
            valid = True
        else:
            concept = "Other"
            valid = False

        return {
            "valid": valid,
            "language": "English",
            "detected_concept": concept,
            "normalized_value": candidate,
            "solution_bias": False,
            "reason": "",
            "suggestion": "",
        }


class CompoundFakeLLM(FakeLLM):
    def _json_chat(self, messages, schema):
        return {
            "candidates": [
                {
                    "mention": "research and development center",
                    "candidate_concept": "OperationalEntity",
                    "reason": "One established compound phrase.",
                }
            ]
        }

    def validate_participant(self, candidate, context=""):
        # One side is not independently a participant/context element, so the
        # generic splitter must preserve the compound phrase.
        if candidate.strip().casefold() == "development center":
            concept = "OperationalEntity"
            valid = True
        else:
            concept = "Other"
            valid = False
        return {
            "valid": valid,
            "language": "English",
            "detected_concept": concept,
            "normalized_value": candidate,
            "solution_bias": False,
            "reason": "",
            "suggestion": "",
        }


def main() -> None:
    goal = "Support staff and facilities"

    raw = [
        {
            "mention": "staff",
            "candidate_concept": "OperationalActor",
            "reason": "Human group explicitly mentioned in the goal.",
        },
        {
            "mention": "facilities",
            "candidate_concept": "OperationalEntity",
            "reason": "Context element explicitly mentioned in the goal.",
        },
        {
            "mention": "command center",
            "candidate_concept": "OperationalEntity",
            "reason": "Invented by the model and not present in the goal.",
        },
    ]

    candidates = filter_goal_candidates(goal, raw)
    assert [item["mention"] for item in candidates] == ["staff", "facilities"]
    assert candidates[0]["candidate_concept"] == "OperationalActor"
    assert candidates[1]["candidate_concept"] == "OperationalEntity"

    # If a compact model merges coordinated candidates, semantic classification
    # of each side must recover them without relying on a domain vocabulary.
    merged = extract_goal_candidates(FakeLLM(), goal)
    assert [item["mention"] for item in merged] == ["staff", "facilities"]
    assert [item["candidate_concept"] for item in merged] == [
        "OperationalActor",
        "OperationalEntity",
    ]

    duplicate_filtered = filter_goal_candidates(
        goal,
        raw,
        existing_names=["staff"],
    )
    assert [item["mention"] for item in duplicate_filtered] == ["facilities"]

    compound_goal = "Maintain research and development center readiness"
    compound = extract_goal_candidates(CompoundFakeLLM(), compound_goal)
    assert [item["mention"] for item in compound] == [
        "research and development center"
    ]

    print("Candidate discovery test passed.")


if __name__ == "__main__":
    main()
