from fast_input import fast_operational_goal_result
from validator import validate_llm_candidate


def llm_false_language_result(value: str) -> dict:
    return {
        "valid": True,
        "language": "Non-English",
        "detected_concept": "OperationalCapability",
        "normalized_value": value,
        "solution_bias": False,
        "reason": "Incorrect compact-model language guess.",
        "suggestion": "",
    }


def main() -> None:
    neutral_goals = (
        "Maintain neutral operational condition",
        "Keep generic operation stable",
        "Reduce generic processing delay",
    )
    for goal in neutral_goals:
        result = fast_operational_goal_result(goal)
        assert result is not None, goal
        assert result["valid"] is True, goal
        assert result["detected_concept"] == "OperationalCapability", goal
        assert result["solution_bias"] is False, goal

    english_goal = "Keep generic operation stable"
    validated = validate_llm_candidate(
        english_goal,
        "OperationalCapability",
        llm_false_language_result(english_goal),
    )
    assert validated.accepted, validated

    assert fast_operational_goal_result("Keep software available") is None
    assert fast_operational_goal_result("Manter a area segura para todos") is None

    print("Goal fast-path test passed.")


if __name__ == "__main__":
    main()
