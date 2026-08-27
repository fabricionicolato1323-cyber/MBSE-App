from participant_rules import (
    classify_participant,
    looks_like_plural_participant_label,
    participant_nature_for_type,
)


def main() -> None:
    actor = classify_participant("Rescue Coordinator")
    assert actor.concept == "OperationalActor", actor
    assert actor.nature == "human_individual", actor
    assert actor.evidence_level == "strong", actor

    team = classify_participant("Medical Team")
    assert team.concept == "OperationalEntity", team
    assert team.nature == "team_or_collective", team

    brigade = classify_participant("Fire Brigade")
    assert brigade.concept == "OperationalEntity", brigade
    assert brigade.nature == "team_or_collective", brigade
    assert brigade.evidence_level == "strong", brigade

    organization = classify_participant("Aviation Authority")
    assert organization.concept == "OperationalEntity", organization
    assert organization.nature == "organization", organization

    tower = classify_participant("Control Tower")
    assert tower.concept == "OperationalEntity", tower
    assert tower.nature == "infrastructure_or_facility", tower
    assert tower.evidence_level == "partial", tower

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

    assert looks_like_plural_participant_label("Field soldiers")
    assert not looks_like_plural_participant_label("Operations Coordinator")
    assert not looks_like_plural_participant_label("Status")
    assert (
        participant_nature_for_type("Field soldiers", "OperationalEntity")
        == "team_or_collective"
    )

    print("Participant rules test passed.")


if __name__ == "__main__":
    main()
