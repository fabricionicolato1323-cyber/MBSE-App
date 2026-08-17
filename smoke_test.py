import sys
import types

try:
    import llama_cpp  # type: ignore
except ImportError:
    sys.modules["llama_cpp"] = types.SimpleNamespace(Llama=object)

from graph_model import OAGraph
from validator import validate_llm_candidate, validate_participant_candidate
from llm_service import LocalLLM


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
        "Keep restricted airspace safe",
        "OperationalCapability",
        ok_result("OperationalCapability", "Keep restricted airspace safe"),
    )
    assert goal_validation.accepted

    participant_validation = validate_participant_candidate(
        "Air Traffic Controller",
        ok_result("OperationalActor", "Air Traffic Controller", "Language-neutral"),
    )
    assert participant_validation.accepted

    activity_validation = validate_llm_candidate(
        "Assess potential airspace threats",
        "OperationalActivity",
        ok_result("OperationalActivity", "Assess potential airspace threats"),
    )
    assert activity_validation.accepted

    # Regression cases observed with the real Qwen2.5-3B model.
    # 1) Small model incorrectly labels a short English phrase as Non-English.
    r = validate_llm_candidate(
        "informs drone informations",
        "OperationalActivity",
        {
            **ok_result("OperationalActivity", "Inform drone information"),
            "language": "Non-English",
            "valid": False,
            "reason": "Please answer in English only.",
            "suggestion": "detects hostile drones",
        },
    )
    assert r.accepted, r

    # 2) Small model calls a valid broad action too vague.
    r = validate_llm_candidate(
        "provide drone information",
        "OperationalActivity",
        {
            **ok_result("OperationalActivity", "Provide drone information"),
            "valid": False,
            "reason": "This answer is too vague.",
            "suggestion": "Detect hostile drones",
        },
    )
    assert r.accepted, r

    # 3) Small model mistakes an action for an exchanged item because its object is information.
    r = validate_llm_candidate(
        "provide drone information such as position and velocity",
        "OperationalActivity",
        {
            **ok_result("OperationalExchange", "Drone information such as position and velocity"),
            "valid": False,
            "reason": "This answer describes an exchange rather than an action.",
            "suggestion": "Assess incoming threat information",
        },
    )
    assert r.accepted, r
    assert r.detected_concept == "OperationalActivity"

    # Obvious Portuguese should still be rejected.
    rejected_language = validate_llm_candidate(
        "fornecer informações sobre a posição e velocidade",
        "OperationalActivity",
        {
            **ok_result("OperationalActivity", "fornecer informações sobre a posição e velocidade"),
            "language": "Non-English",
        },
    )
    assert not rejected_language.accepted

    air_traffic_control = validate_participant_candidate(
        "Air traffic control",
        {
            **ok_result("OperationalActor", "Air Traffic Control", "English"),
            "valid": False,
            "reason": "This is not phrased as a human role.",
        },
    )
    assert air_traffic_control.accepted
    assert air_traffic_control.detected_concept == "OperationalEntity"

    drone_traffic_control = validate_participant_candidate(
        "Drone traffic control",
        {
            **ok_result("OperationalActor", "Drone Traffic Control", "English"),
            "valid": False,
        },
    )
    assert drone_traffic_control.accepted
    assert drone_traffic_control.detected_concept == "OperationalEntity"

    parsed = LocalLLM._parse_json(
        '{"valid":true,"language":"English","detected_concept":"OperationalEntity",'
        '"normalized_value":"Air Traffic Control","solution_bias":false,'
        '"reason":"line one\nline two","suggestion":""}'
    )
    assert parsed["valid"] is True

    rejected_technical_participant = validate_participant_candidate(
        "drone detection systems",
        ok_result("OperationalEntity", "Drone Detection Systems", "English"),
    )
    assert not rejected_technical_participant.accepted
    assert not rejected_technical_participant.suggestion

    rejected_solution = validate_llm_candidate(
        "Build a Python script for threat detection",
        "OperationalActivity",
        ok_result("OperationalActivity", "Build a Python script for threat detection"),
    )
    assert not rejected_solution.accepted

    _, goal, _ = graph.add_node("OperationalCapability", "Keep restricted airspace safe")
    _, actor, _ = graph.add_node("OperationalActor", "Air Traffic Controller")
    _, action, _ = graph.add_node("OperationalActivity", "Assess potential airspace threats")

    assert graph.add_relation(actor, "PERFORMS", action)[0]
    assert graph.add_relation(action, "SUPPORTS_CAPABILITY", goal)[0]
    assert not graph.add_relation(goal, "PERFORMS", action)[0]

    duplicate_ok, _, _ = graph.add_node("OperationalActor", "air traffic controller")
    assert not duplicate_ok

    print("Smoke test passed.")


if __name__ == "__main__":
    main()
