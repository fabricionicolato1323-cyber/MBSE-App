from candidate_discovery import extract_goal_candidates, filter_goal_candidates


class FakeLLM:
    """Simulates a compact local model that incorrectly merges two candidates."""

    def _json_chat(self, messages, schema):
        return {
            "candidates": [
                {
                    "mention": "infrastructure and soldiers",
                    "candidate_concept": "OperationalEntity",
                    "reason": "Real-world elements explicitly mentioned in the goal.",
                }
            ]
        }


def main() -> None:
    goal = "Keep infrastructure and soldiers safe"

    # Normal case: the LLM already returns separate candidates.
    raw = [
        {
            "mention": "infrastructure",
            "candidate_concept": "OperationalEntity",
            "reason": "Real-world infrastructure mentioned in the goal.",
        },
        {
            "mention": "soldiers",
            "candidate_concept": "OperationalActor",
            "reason": "Human group explicitly mentioned in the goal.",
        },
        {
            "mention": "safe",
            "candidate_concept": "Other",
            "reason": "Quality, not a participant.",
        },
        {
            "mention": "command center",
            "candidate_concept": "OperationalEntity",
            "reason": "Invented by the model and not present in the goal.",
        },
    ]

    candidates = filter_goal_candidates(goal, raw)
    assert [item["mention"] for item in candidates] == ["infrastructure", "soldiers"]
    assert candidates[0]["candidate_concept"] == "OperationalEntity"
    assert candidates[1]["candidate_concept"] == "OperationalActor"

    # Regression case: Qwen returns one merged phrase. The deterministic barrier
    # must split it into the two independently confirmable model candidates.
    merged = extract_goal_candidates(FakeLLM(), goal)
    assert [item["mention"] for item in merged] == ["infrastructure", "soldiers"]
    assert [item["candidate_concept"] for item in merged] == [
        "OperationalEntity",
        "OperationalActor",
    ]

    duplicate_filtered = filter_goal_candidates(
        goal,
        raw,
        existing_names=["soldiers"],
    )
    assert [item["mention"] for item in duplicate_filtered] == ["infrastructure"]

    # Do not blindly split established compound phrases just because they contain
    # the word "and".
    compound_goal = "Maintain command and control center readiness"
    compound = filter_goal_candidates(
        compound_goal,
        [
            {
                "mention": "command and control center",
                "candidate_concept": "OperationalEntity",
                "reason": "Facility explicitly mentioned in the goal.",
            }
        ],
    )
    assert [item["mention"] for item in compound] == ["command and control center"]

    print("Candidate discovery test passed.")


if __name__ == "__main__":
    main()
