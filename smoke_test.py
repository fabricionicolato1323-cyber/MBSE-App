import sys
import types

try:
    import llama_cpp  # type: ignore
except ImportError:
    sys.modules["llama_cpp"] = types.SimpleNamespace(Llama=object)

from graph_model import OAGraph
from llm_service import LocalLLM
from validator import validate_llm_candidate, validate_participant_candidate


def ok_result(concept: str, value: str, language: str = "English") -> dict:
    return {
        "valid": True,
        "language": language,
        "detected_concept": concept,
        "normalized_value": value,
        "solution_bias": False,
        "reason": "",
        "suggestion": "",
    }


def main() -> None:
    graph = OAGraph()

    goal_validation = validate_llm_candidate(
        "Maintain safe and effective operations",
        "OperationalCapability",
        ok_result(
            "OperationalCapability",
            "Maintain safe and effective operations",
        ),
    )
    assert goal_validation.accepted

    participant_validation = validate_participant_candidate(
        "Operations Coordinator",
        ok_result(
            "OperationalActor",
            "Operations Coordinator",
            "Language-neutral",
        ),
    )
    assert participant_validation.accepted

    short_participant = validate_participant_candidate(
        "Service Group",
        {
            **ok_result("OperationalEntity", "Service Group", "English"),
            "valid": False,
            "reason": "The label is too short.",
        },
    )
    assert short_participant.accepted
    assert short_participant.detected_concept == "OperationalEntity"

    activity_validation = validate_llm_candidate(
        "Coordinate operational response",
        "OperationalActivity",
        ok_result(
            "OperationalActivity",
            "Coordinate operational response",
        ),
    )
    assert activity_validation.accepted

    unfamiliar_action = validate_llm_candidate(
        "Reconcile service records",
        "OperationalActivity",
        ok_result(
            "OperationalActivity",
            "Reconcile service records",
        ),
    )
    assert unfamiliar_action.accepted

    first_negative = {
        **ok_result("Other", "Reconcile service records"),
        "valid": False,
        "reason": "Uncertain classification.",
    }
    assert LocalLLM._needs_semantic_recheck(
        first_negative,
        "OperationalActivity",
    )
    assert not LocalLLM._needs_semantic_recheck(
        ok_result("OperationalActivity", "Reconcile service records"),
        "OperationalActivity",
    )

    rejected_language = validate_llm_candidate(
        "fornecer informações para o grupo",
        "OperationalActivity",
        {
            **ok_result(
                "OperationalActivity",
                "fornecer informações para o grupo",
            ),
            "language": "Non-English",
        },
    )
    assert not rejected_language.accepted

    parsed = LocalLLM._parse_json(
        '{"valid":true,"language":"English","detected_concept":"OperationalEntity",'
        '"normalized_value":"Service Group","solution_bias":false,'
        '"reason":"line one\nline two","suggestion":""}'
    )
    assert parsed["valid"] is True

    rejected_technical_participant = validate_participant_candidate(
        "software platform",
        ok_result("OperationalEntity", "Software Platform", "English"),
    )
    assert not rejected_technical_participant.accepted

    rejected_solution = validate_llm_candidate(
        "Build a Python script for processing",
        "OperationalActivity",
        ok_result(
            "OperationalActivity",
            "Build a Python script for processing",
        ),
    )
    assert not rejected_solution.accepted

    _, goal, _ = graph.add_node(
        "OperationalCapability",
        "Maintain safe and effective operations",
    )
    _, facility, _ = graph.add_node(
        "OperationalEntity",
        "Operations Facility",
        expects_activity=False,
    )
    _, group, _ = graph.add_node(
        "OperationalEntity",
        "Service Group",
        expects_activity=True,
    )
    _, area, _ = graph.add_node(
        "OperationalEntity",
        "Work Area",
        expects_activity=False,
    )
    _, actor, _ = graph.add_node(
        "OperationalActor",
        "Operations Coordinator",
    )
    _, second_actor, _ = graph.add_node(
        "OperationalActor",
        "Shift Supervisor",
    )
    _, action, _ = graph.add_node(
        "OperationalActivity",
        "Coordinate operational response",
        semantic_frame=True,
        semantic_verb="Coordinate",
        semantic_objects=["operational response", "service priorities"],
        semantic_recipients=["Service Group"],
        semantic_locations=["Work Area"],
        semantic_conditions=["when escalation is required"],
        semantic_time=["during active operations"],
        semantic_other_complements=[],
        source_text="Coordinate operational response and service priorities",
    )

    assert graph.add_relation(actor, "PERFORMS", action)[0]
    assert graph.add_relation(second_actor, "PERFORMS", action)[0]
    assert graph.add_relation(action, "SUPPORTS_CAPABILITY", goal)[0]

    performers = graph.participants_for_activity(action)
    assert set(performers) == {actor, second_actor}
    assert "Operations Coordinator" in graph.action_label(action)
    assert "Shift Supervisor" in graph.action_label(action)

    semantics = graph.activity_semantics(action)
    assert semantics["semantic_verb"] == "Coordinate"
    assert semantics["semantic_objects"] == [
        "operational response",
        "service priorities",
    ]
    assert semantics["semantic_recipients"] == ["Service Group"]
    assert semantics["semantic_locations"] == ["Work Area"]

    assert graph.add_relation(facility, "CONTAINS", group)[0]
    assert graph.add_relation(group, "CONTAINS", actor)[0]
    assert graph.structural_parent(actor) == group

    assert graph.add_relation(actor, "LOCATED_IN", area)[0]
    assert graph.locations_for(actor) == [area]

    assert not graph.add_relation(actor, "CONTAINS", group)[0]

    _, other_org, _ = graph.add_node(
        "OperationalEntity",
        "Other Organization",
        expects_activity=True,
    )
    assert not graph.add_relation(other_org, "CONTAINS", actor)[0]

    assert not graph.add_relation(group, "CONTAINS", facility)[0]

    assert graph.add_relation(area, "LOCATED_IN", facility)[0]
    assert not graph.add_relation(facility, "LOCATED_IN", area)[0]

    notes = graph.completeness_messages()
    assert not any("Operations Facility' has no action" in note for note in notes)
    assert not any("Work Area' has no action" in note for note in notes)

    assert not graph.add_relation(goal, "PERFORMS", action)[0]

    duplicate_ok, _, _ = graph.add_node(
        "OperationalActor",
        "operations coordinator",
    )
    assert not duplicate_ok

    shown = graph.friendly_show()
    assert "Operations Facility contains Service Group" in shown
    assert "Operations Coordinator operates in Work Area" in shown
    assert "Shift Supervisor" in shown
    assert "objects: operational response, service priorities" in shown

    print("Smoke test passed.")


if __name__ == "__main__":
    main()
