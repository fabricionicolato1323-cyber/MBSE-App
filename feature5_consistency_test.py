from __future__ import annotations

from pathlib import Path

from graph_model import OAGraph
from knowledge_graph import ArcadiaKnowledgeBase, OA
from model_consistency import (
    CAPABILITY_DECOMPOSITION,
    compare_model_consistently,
    format_model_comparison,
    project_rdf_with_decomposition,
    structural_issues,
)


BASE_DIR = Path(__file__).resolve().parent


def build_model() -> tuple[OAGraph, dict[str, str]]:
    model = OAGraph()
    _, goal_parent, _ = model.add_node("OperationalCapability", "Achieve outcome A")
    _, goal_child, _ = model.add_node("OperationalCapability", "Achieve outcome B")
    _, entity, _ = model.add_node(
        "OperationalEntity",
        "Participant Group A",
        expects_activity=True,
        nature="team_or_collective",
    )
    _, actor, _ = model.add_node("OperationalActor", "Participant Role A")
    _, action_parent, _ = model.add_node("OperationalActivity", "Perform action A")
    _, action_child, _ = model.add_node("OperationalActivity", "Perform action B")

    assert model.add_relation(goal_parent, "DECOMPOSES", goal_child)[0]
    assert model.add_relation(action_parent, "DECOMPOSES", action_child)[0]
    assert model.add_relation(entity, "CONTAINS", actor)[0]
    assert model.add_relation(actor, "PERFORMS", action_parent)[0]
    assert model.add_relation(actor, "PERFORMS", action_child)[0]
    assert model.add_relation(action_parent, "SUPPORTS_CAPABILITY", goal_parent)[0]
    assert model.add_relation(action_child, "SUPPORTS_CAPABILITY", goal_child)[0]

    return model, {
        "goal_parent": goal_parent,
        "goal_child": goal_child,
        "entity": entity,
        "actor": actor,
        "action_parent": action_parent,
        "action_child": action_child,
    }


def main() -> None:
    knowledge = ArcadiaKnowledgeBase(BASE_DIR / "knowledge_base")
    model, ids = build_model()

    # 1. Every supported hierarchy is represented in RDF.
    project = project_rdf_with_decomposition(knowledge, model)
    assert (
        knowledge._project_uri(ids["goal_parent"]),
        CAPABILITY_DECOMPOSITION,
        knowledge._project_uri(ids["goal_child"]),
    ) in project
    assert (
        knowledge._project_uri(ids["action_parent"]),
        OA.containsActivity,
        knowledge._project_uri(ids["action_child"]),
    ) in project
    assert (
        knowledge._project_uri(ids["entity"]),
        OA.containsEntity,
        knowledge._project_uri(ids["actor"]),
    ) in project

    # 2. A valid hierarchy does not create a mandatory-rule violation.
    valid = compare_model_consistently(knowledge, model)
    assert valid.conforms
    assert valid.count("VIOLATION") == 0

    # 3. Imported/bypassed cross-type decomposition is detected deterministically.
    model.graph.add_edge(ids["goal_parent"], ids["action_child"], type="DECOMPOSES")
    issues = structural_issues(model)
    assert any("goals to goals or actions to actions" in issue.message for issue in issues)
    invalid = compare_model_consistently(knowledge, model)
    assert not invalid.conforms
    model.graph.remove_edge(ids["goal_parent"], ids["action_child"])

    # 4. Multiple decomposition parents are detected by the integrated comparison.
    _, another_action, _ = model.add_node("OperationalActivity", "Perform action C")
    model.graph.add_edge(another_action, ids["action_child"], type="DECOMPOSES")
    multi_parent = compare_model_consistently(knowledge, model)
    assert not multi_parent.conforms
    assert any("more than one decomposition parent" in issue.message for issue in multi_parent.issues)
    model.graph.remove_edge(another_action, ids["action_child"])

    # 5. Cycles that bypass the write barrier are detected.
    model.graph.add_edge(ids["action_child"], ids["action_parent"], type="DECOMPOSES")
    cyclic = compare_model_consistently(knowledge, model)
    assert not cyclic.conforms
    assert any("Action decomposition contains a cycle" in issue.message for issue in cyclic.issues)
    model.graph.remove_edge(ids["action_child"], ids["action_parent"])

    # 6. Malformed CONTAINS relations are detected.
    model.graph.add_edge(ids["entity"], ids["action_parent"], type="CONTAINS")
    malformed = structural_issues(model)
    assert any("CONTAINS must connect" in issue.message for issue in malformed)

    # 7. New comparison presentation stays method-neutral for lower cognitive load.
    formatted = format_model_comparison(valid)
    assert "Mandatory model rules" in formatted
    assert "Arcadia" not in formatted
    assert "Elapsed comparison time" in formatted

    print("Feature 5 consistency test passed (7 checks).")


if __name__ == "__main__":
    main()
