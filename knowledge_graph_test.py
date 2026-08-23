from __future__ import annotations

from pathlib import Path

from pyshacl import validate as shacl_validate

from graph_model import OAGraph
from knowledge_graph import ArcadiaKnowledgeBase


BASE_DIR = Path(__file__).resolve().parent


class GroundedLLMStub:
    def answer_from_knowledge(self, question: str, evidence: list[dict]) -> dict:
        assert question
        assert evidence
        return {
            "coverage": "SUPPORTED",
            "answer": (
                "An Operational Actor is a non-decomposable specialization of "
                "Operational Entity, usually representing a human role."
            ),
            "claim_ids": [item["claim_id"] for item in evidence],
        }


class InvalidCitationLLMStub:
    def answer_from_knowledge(self, question: str, evidence: list[dict]) -> dict:
        return {
            "coverage": "SUPPORTED",
            "answer": "This answer cites evidence that was not retrieved.",
            "claim_ids": ["CLAIM-NOT-IN-EVIDENCE"],
        }


def build_small_model() -> OAGraph:
    model = OAGraph()
    _, goal, _ = model.add_node(
        "OperationalCapability",
        "Maintain safe operations",
    )
    _, actor, _ = model.add_node(
        "OperationalActor",
        "Operations Coordinator",
    )
    _, entity, _ = model.add_node(
        "OperationalEntity",
        "Response Team",
        expects_activity=True,
    )
    _, first_action, _ = model.add_node(
        "OperationalActivity",
        "Assess operational status",
    )
    _, second_action, _ = model.add_node(
        "OperationalActivity",
        "Coordinate operational response",
    )
    assert model.add_relation(actor, "PERFORMS", first_action)[0]
    assert model.add_relation(entity, "PERFORMS", second_action)[0]
    assert model.add_relation(first_action, "SUPPORTS_CAPABILITY", goal)[0]
    assert model.add_relation(second_action, "SUPPORTS_CAPABILITY", goal)[0]
    assert model.add_relation(
        first_action,
        "OPERATIONAL_EXCHANGE",
        second_action,
        name="Status information",
    )[0]
    assert model.add_relation(
        actor,
        "COMMUNICATION_MEAN",
        entity,
        name="Direct communication",
    )[0]
    return model


def main() -> None:
    knowledge = ArcadiaKnowledgeBase(BASE_DIR / "knowledge_base")
    stats = knowledge.stats()
    assert stats["ontology_triples"] > 300
    assert stats["reference_triples"] > 200
    assert stats["shape_triples"] > 150
    assert stats["claims"] >= 25

    conforms, _, report_text = shacl_validate(
        data_graph=knowledge.reference,
        shacl_graph=knowledge.shapes,
        ont_graph=knowledge.ontology,
        inference="rdfs",
        advanced=True,
    )
    assert conforms, report_text

    actor_entity = knowledge.retrieve(
        "What is the difference between an Operational Actor and an Operational Entity?"
    )
    assert actor_entity.coverage == "SUPPORTED"
    assert "actor_vs_entity" in actor_entity.resolved_intents
    claim_ids = {claim.claim_id for claim in actor_entity.claims}
    assert "CLAIM-OA-ACTOR-001" in claim_ids
    assert "CLAIM-OA-ACTOR-ENTITY-DIFF-001" in claim_ids

    unknown = knowledge.retrieve("Explain quantum entanglement in particle physics")
    assert unknown.coverage == "NOT_FOUND"
    assert not unknown.claims

    grounded_answer = knowledge.answer(
        "What is the difference between an actor and an entity?",
        GroundedLLMStub(),
    )
    assert "Coverage: SUPPORTED" in grounded_answer
    assert "CLAIM-OA-ACTOR-001" in grounded_answer
    assert "Timing:" in grounded_answer

    rejected_answer = knowledge.answer(
        "What is an Operational Actor?",
        InvalidCitationLLMStub(),
    )
    assert "no unverified answer was shown" in rejected_answer
    assert "CLAIM-NOT-IN-EVIDENCE" not in rejected_answer

    model = build_small_model()
    comparison = knowledge.compare_model(model)
    assert comparison.conforms
    assert comparison.count("VIOLATION") == 0
    assert comparison.project_triples > 30
    assert comparison.elapsed_ms >= 0

    # Simulate an invalid imported graph that bypassed OAGraph's write barrier.
    actor = model.nodes_of_type("OperationalActor")[0]
    entity = model.nodes_of_type("OperationalEntity")[0]
    model.graph.add_edge(actor, entity, type="CONTAINS")
    invalid = knowledge.compare_model(model)
    assert not invalid.conforms
    assert any(
        issue.severity == "VIOLATION" and "must not contain" in issue.message
        for issue in invalid.issues
    )

    print("Knowledge graph test passed.")


if __name__ == "__main__":
    main()
