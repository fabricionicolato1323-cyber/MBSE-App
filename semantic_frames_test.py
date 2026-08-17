from semantic_frames import (
    frame_is_complex,
    normalize_semantic_frames,
)


def base_result(clauses):
    return {
        "valid": True,
        "language": "English",
        "solution_bias": False,
        "reason": "",
        "clauses": clauses,
    }


def clause(
    *,
    subjects=None,
    verb,
    objects=None,
    recipients=None,
    locations=None,
    conditions=None,
    time=None,
    other_complements=None,
    activity_text,
):
    return {
        "subjects": subjects or [],
        "verb": verb,
        "objects": objects or [],
        "recipients": recipients or [],
        "locations": locations or [],
        "conditions": conditions or [],
        "time": time or [],
        "other_complements": other_complements or [],
        "activity_text": activity_text,
    }


def main() -> None:
    # One verb + several objects remains one activity.
    one_verb = normalize_semantic_frames(
        base_result(
            [
                clause(
                    verb="Monitor",
                    objects=["temperature", "pressure"],
                    activity_text="Monitor temperature and pressure",
                )
            ]
        ),
        default_subject="Operator",
    )
    assert one_verb["valid"]
    assert len(one_verb["clauses"]) == 1
    assert one_verb["clauses"][0]["subjects"] == ["Operator"]
    assert one_verb["clauses"][0]["objects"] == ["temperature", "pressure"]
    assert frame_is_complex(one_verb)

    # Several independent verbs become separate activities, and an omitted
    # subject in the second clause inherits the subject from the first clause.
    several_verbs = normalize_semantic_frames(
        base_result(
            [
                clause(
                    subjects=["Operator"],
                    verb="Monitor",
                    objects=["temperature"],
                    activity_text="Monitor temperature",
                ),
                clause(
                    verb="Report",
                    objects=["pressure"],
                    recipients=["Operations"],
                    activity_text="Report pressure to operations",
                ),
            ]
        ),
        default_subject="Operator",
    )
    assert len(several_verbs["clauses"]) == 2
    assert several_verbs["clauses"][1]["subjects"] == ["Operator"]
    assert several_verbs["clauses"][1]["recipients"] == ["Operations"]

    # Several subjects performing the same verb remain one shared activity.
    several_subjects = normalize_semantic_frames(
        base_result(
            [
                clause(
                    subjects=["Operator", "Supervisor"],
                    verb="Approve",
                    objects=["request"],
                    activity_text="Approve request",
                )
            ]
        ),
        default_subject="Operator",
    )
    assert len(several_subjects["clauses"]) == 1
    assert several_subjects["clauses"][0]["subjects"] == [
        "Operator",
        "Supervisor",
    ]

    # Complements stay typed instead of being flattened into the object list.
    complements = normalize_semantic_frames(
        base_result(
            [
                clause(
                    verb="Inspect",
                    objects=["equipment"],
                    locations=["service area"],
                    conditions=["when requested"],
                    time=["before operation"],
                    activity_text="Inspect equipment",
                )
            ]
        ),
        default_subject="Technician",
    )
    parsed = complements["clauses"][0]
    assert parsed["objects"] == ["equipment"]
    assert parsed["locations"] == ["service area"]
    assert parsed["conditions"] == ["when requested"]
    assert parsed["time"] == ["before operation"]

    print("Semantic frame test passed.")


if __name__ == "__main__":
    main()
