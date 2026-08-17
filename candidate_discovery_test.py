from candidate_discovery import filter_goal_candidates


def main() -> None:
    goal = "Keep infrastructure and soldiers safe"
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

    duplicate_filtered = filter_goal_candidates(
        goal,
        raw,
        existing_names=["soldiers"],
    )
    assert [item["mention"] for item in duplicate_filtered] == ["infrastructure"]

    print("Candidate discovery test passed.")


if __name__ == "__main__":
    main()
