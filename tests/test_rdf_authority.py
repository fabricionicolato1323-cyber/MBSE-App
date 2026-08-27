from __future__ import annotations

from pathlib import Path

from rdflib import RDF

from graph_model import OAGraph
from knowledge_graph import ArcadiaKnowledgeBase, OA


BASE_DIR = Path(__file__).resolve().parents[1]


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
        nature="team_or_collective",
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


def test_dataset_exposes_seven_authority_graphs() -> None:
    knowledge = ArcadiaKnowledgeBase(BASE_DIR / "knowledge_base")
    assert knowledge.stats()["named_graphs"] == 7
    assert set(knowledge.named_graph_iris()) == {
        "urn:graph:ontology",
        "urn:graph:arcadia-reference",
        "urn:graph:arcadia-shapes",
        "urn:graph:project-approved",
        "urn:graph:project-candidates",
        "urn:graph:validation",
        "urn:graph:audit",
    }


def test_candidate_graph_never_becomes_approved_project_fact() -> None:
    knowledge = ArcadiaKnowledgeBase(BASE_DIR / "knowledge_base")
    model = build_small_model()
    resource = knowledge.stage_candidate(
        "cand-1",
        "OperationalEntity",
        "Unapproved Team",
        evidence="The text mentioned an unconfirmed team.",
        source="ollama_advisory",
    )

    assert knowledge.candidate_count() == 1
    assert (resource, RDF.type, OA.CandidateMention) in knowledge.candidates

    approved = knowledge.project_rdf(model)
    assert not any(
        str(value) == "Unapproved Team"
        for value in approved.objects(None, OA.name)
    )
    assert knowledge.candidate_count() == 1


def test_compare_populates_only_derived_project_and_validation_layers() -> None:
    knowledge = ArcadiaKnowledgeBase(BASE_DIR / "knowledge_base")
    model = build_small_model()
    knowledge.stage_candidate(
        "cand-2",
        "OperationalActor",
        "Unapproved Observer",
    )

    comparison = knowledge.compare_model(model)
    assert comparison.project_triples > 30
    assert len(knowledge.project) == comparison.project_triples
    assert len(knowledge.validation) > 0
    assert knowledge.candidate_count() == 1
    assert len(knowledge.audit) > 0


def test_export_writes_json_turtle_and_validation_report(tmp_path: Path) -> None:
    knowledge = ArcadiaKnowledgeBase(BASE_DIR / "knowledge_base")
    model = build_small_model()
    knowledge.stage_candidate(
        "cand-export",
        "OperationalEntity",
        "Unapproved Export Candidate",
    )

    artifacts = knowledge.export_approved_model(model, tmp_path)
    assert artifacts.json_path.name == "oa_model.json"
    assert artifacts.turtle_path.name == "oa_project_approved.ttl"
    assert artifacts.validation_report_path.name == "oa_validation_report.md"
    assert artifacts.json_path.exists()
    assert artifacts.turtle_path.exists()
    assert artifacts.validation_report_path.exists()

    turtle = artifacts.turtle_path.read_text(encoding="utf-8")
    report = artifacts.validation_report_path.read_text(encoding="utf-8")
    assert "Unapproved Export Candidate" not in turtle
    assert "Candidate statements are excluded" in report
    assert "# OA Validation Report" in report
