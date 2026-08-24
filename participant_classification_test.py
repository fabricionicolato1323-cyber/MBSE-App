from validator import validate_participant_candidate


def main() -> None:
    # Regression pattern observed with the compact local model: it correctly
    # recognizes that the phrase is a profession but incorrectly concludes that a
    # profession is not an operational participant. In OA, a profession/job title
    # is a human role and therefore an OperationalActor.
    profession_false_negative = {
        "valid": False,
        "language": "English",
        "detected_concept": "Other",
        "normalized_value": "Air traffic controller",
        "solution_bias": False,
        "reason": (
            "Air traffic controller is a profession and not a real-world "
            "operational element in the given context."
        ),
        "suggestion": "",
    }
    result = validate_participant_candidate(
        "Air traffic controller",
        profession_false_negative,
    )
    assert result.accepted, result
    assert result.detected_concept == "OperationalActor", result

    # The repair is semantic and generic, not tied to one profession name.
    generic_job_title_false_negative = {
        "valid": False,
        "language": "English",
        "detected_concept": "Other",
        "normalized_value": "Service coordinator",
        "solution_bias": False,
        "reason": "This is a job title rather than a named physical individual.",
        "suggestion": "",
    }
    result = validate_participant_candidate(
        "Service coordinator",
        generic_job_title_false_negative,
    )
    assert result.accepted, result
    assert result.detected_concept == "OperationalActor", result

    # A proposed technical solution must still be rejected.
    technical = {
        "valid": True,
        "language": "English",
        "detected_concept": "OperationalEntity",
        "normalized_value": "Proposed platform",
        "solution_bias": False,
        "reason": "",
        "suggestion": "",
    }
    result = validate_participant_candidate("Proposed platform", technical)
    assert not result.accepted, result

    # An explicitly existing external technical participant is not automatically
    # solution bias in Operational Analysis.
    existing = {
        **technical,
        "normalized_value": "Existing external radar",
    }
    result = validate_participant_candidate("Existing external radar", existing)
    assert result.accepted, result

    # A compact model may understand the human meaning but miss the plural/type
    # rule. The deterministic reconciliation is grammatical, not domain-specific.
    plural_human_actor = {
        "valid": True,
        "language": "English",
        "detected_concept": "OperationalActor",
        "normalized_value": "Field soldiers",
        "solution_bias": False,
        "reason": "This phrase names human role-holders.",
        "suggestion": "",
    }
    result = validate_participant_candidate("Field soldiers", plural_human_actor)
    assert result.accepted, result
    assert result.detected_concept == "OperationalEntity", result
    assert "multiple human role-holders" in result.reason, result

    print("Participant classification test passed.")


if __name__ == "__main__":
    main()
