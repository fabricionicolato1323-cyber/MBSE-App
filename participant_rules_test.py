import json
import os
import tempfile
from pathlib import Path

from participant_rules import (
    LEXICON_ENV,
    LEXICON_EXTENSION_ENV,
    classify_participant,
    load_lexicon,
    looks_like_plural_participant_label,
    participant_nature_for_type,
)


def main() -> None:
    actor = classify_participant("Process Coordinator")
    assert actor.concept == "OperationalActor", actor
    assert actor.nature == "human_individual", actor
    assert actor.evidence_level == "strong", actor

    team = classify_participant("Support Team")
    assert team.concept == "OperationalEntity", team
    assert team.nature == "team_or_collective", team

    organization = classify_participant("Service Authority")
    assert organization.concept == "OperationalEntity", organization
    assert organization.nature == "organization", organization

    unit = classify_participant("Service Department")
    assert unit.concept == "OperationalEntity", unit
    assert unit.nature == "organizational_unit", unit

    facility = classify_participant("Operations Center")
    assert facility.concept == "OperationalEntity", facility
    assert facility.nature == "infrastructure_or_facility", facility

    existing = classify_participant("Existing external system")
    assert existing.concept == "OperationalEntity", existing
    assert existing.nature == "existing_technical_system", existing

    ambiguous = classify_participant("Support system")
    assert ambiguous.concept is None, ambiguous
    assert ambiguous.evidence_level == "ambiguous", ambiguous

    proposed = classify_participant("Proposed platform")
    assert proposed.concept is None, proposed
    assert proposed.solution_bias, proposed

    communication = classify_participant("Communication channel")
    assert communication.concept is None, communication
    assert "communication" in communication.reason.casefold(), communication

    unknown = classify_participant("Regional partner")
    assert not unknown.actionable, unknown

    assert looks_like_plural_participant_label("Field workers")
    assert not looks_like_plural_participant_label("Process Coordinator")
    assert not looks_like_plural_participant_label("Status")
    assert (
        participant_nature_for_type("Field workers", "OperationalEntity")
        == "team_or_collective"
    )

    previous_base = os.environ.get(LEXICON_ENV)
    previous_extension = os.environ.get(LEXICON_EXTENSION_ENV)

    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)

        replacement = directory / "replacement.json"
        replacement.write_text(
            json.dumps({"actor_heads": ["configuredrole"]}),
            encoding="utf-8",
        )
        os.environ[LEXICON_ENV] = str(replacement)
        os.environ.pop(LEXICON_EXTENSION_ENV, None)
        load_lexicon.cache_clear()

        configured = classify_participant("Neutral ConfiguredRole")
        assert configured.concept == "OperationalActor", configured
        assert not classify_participant("Process Coordinator").actionable

        extension = directory / "extensions.json"
        extension.write_text(
            json.dumps(
                {
                    "collective_heads": ["configuredcollective"],
                    "facility_heads": ["configuredfacility"],
                }
            ),
            encoding="utf-8",
        )
        os.environ[LEXICON_EXTENSION_ENV] = str(extension)
        load_lexicon.cache_clear()

        collective = classify_participant("Neutral ConfiguredCollective")
        facility = classify_participant("Neutral ConfiguredFacility")
        assert collective.concept == "OperationalEntity", collective
        assert collective.nature == "team_or_collective", collective
        assert facility.concept == "OperationalEntity", facility
        assert facility.nature == "infrastructure_or_facility", facility

    if previous_base is None:
        os.environ.pop(LEXICON_ENV, None)
    else:
        os.environ[LEXICON_ENV] = previous_base

    if previous_extension is None:
        os.environ.pop(LEXICON_EXTENSION_ENV, None)
    else:
        os.environ[LEXICON_EXTENSION_ENV] = previous_extension

    load_lexicon.cache_clear()
    print("Participant rules test passed.")


if __name__ == "__main__":
    main()
