from participant_rules import classify_participant


def main() -> None:
    actor = classify_participant("Rescue Coordinator")
    assert actor.concept == "OperationalActor", actor
    assert actor.nature == "human_individual", actor
    assert actor.evidence_level == "strong", actor

    team = classify_participant("Medical Team")
    assert team.concept == "OperationalEntity", team
    assert team.nature == "team_or_collective", team

    organization = classify_participant("Aviation Authority")
    assert organization.concept == "OperationalEntity", organization
    assert organization.nature == "organization", organization

    existing = classify_participant("Existing external radar")
    assert existing.concept == "OperationalEntity", existing
    assert existing.nature == "existing_technical_system", existing

    ambiguous = classify_participant("Surveillance system")
    assert ambiguous.concept is None, ambiguous
    assert ambiguous.evidence_level == "ambiguous", ambiguous

    proposed = classify_participant("Proposed platform")
    assert proposed.concept is None, proposed
    assert proposed.solution_bias, proposed

    communication = classify_participant("Emergency radio")
    assert communication.concept is None, communication
    assert "communication" in communication.reason.casefold(), communication

    unknown = classify_participant("Regional partner")
    assert not unknown.actionable, unknown

    print("Participant rules test passed.")


if __name__ == "__main__":
    main()
