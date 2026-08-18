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
    # Exact regressions from the photographed terminal session.
    photographed_goals = [
        "Maintain restricted area safe",
        "keep restricted area safe",
        "keep people and assets safe within the restricted area",
    ]

    for goal in photographed_goals:
        result = fast_operational_goal_result(goal)
        assert result is not None, goal
        assert result["valid"] is True, goal
        assert result["detected_concept"] == "OperationalCapability", goal
        assert result["solution_bias"] is False, goal

    # The short-English language barrier must not trust one bad LLM label.
    english_goal = "keep people and assets safe within the restricted area"
    validated = validate_llm_candidate(
        english_goal,
        "OperationalCapability",
        llm_false_language_result(english_goal),
    )
    assert validated.accepted, validated

    # A technical implementation phrase must not be fast-accepted.
    assert fast_operational_goal_result("Keep Python script available") is None

    # A clearly non-English construction must not be fast-accepted.
    assert fast_operational_goal_result("Manter a area segura para pessoas") is None

    # The fast path is grammatical/domain-neutral, not tied to the photographed
    # scenario. Different operational domains should use the same rule.
    for generic_goal in (
        "Reduce service interruption time",
        "Ensure safe clinical operations",
        "Maintain reliable logistics operations",
        "Protect personnel during maintenance",
    ):
        result = fast_operational_goal_result(generic_goal)
        assert result is not None, generic_goal
        assert result["valid"] is True, generic_goal

    print("Goal fast-path test passed.")


if __name__ == "__main__":
    main()
