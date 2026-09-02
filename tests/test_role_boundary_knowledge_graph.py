from __future__ import annotations

from pathlib import Path

from rdflib import RDF

from graph_model import OAGraph
from knowledge_graph import ArcadiaKnowledgeBase, OA
from knowledge_graph_role_boundary import install_role_boundary_knowledge_support
from participant_classification_simple import SimplifiedParticipantClassificationMixin


BASE_DIR = Path(__file__).resolve().parents[1]


def knowledge_base() -> ArcadiaKnowledgeBase:
    install_role_boundary_knowledge_support()
    return ArcadiaKnowledgeBase(BASE_DIR / "knowledge_base")


def test_knowledge_graph_detects_role_labels_without_assuming_human() -> None:
    knowledge = knowledge_base()

    manager = knowledge.assess_participant_phrase("Level Crossing Manager")
    controller = knowledge.assess_participant_phrase("Air Traffic Controller")

    assert manager.kind == "role_realization"
    assert controller.kind == "role_realization"
    assert manager.requires_clarification
    assert controller.requires_clarification
    assert "manager" in manager.matched_cues
    assert "controller" in controller.matched_cues


def test_knowledge_graph_distinguishes_technical_boundary_states() -> None:
    knowledge = knowledge_base()

    ambiguous = knowledge.assess_participant_phrase("Level Crossing System")
    existing = knowledge.assess_participant_phrase("Existing Train Control System")
    solution = knowledge.assess_participant_phrase("System of Interest")

    assert ambiguous.kind == "technical_boundary"
    assert ambiguous.requires_clarification
    assert existing.kind == "existing_technical"
    assert existing.suggested_nature == "existing_technical_system"
    assert solution.kind == "solution_boundary"
    assert solution.requires_clarification


def test_role_boundary_claims_are_retrievable() -> None:
    knowledge = knowledge_base()
    result = knowledge.retrieve("Can a controller be a human or system?")

    assert result.coverage == "SUPPORTED"
    assert "controller_human_or_system" in result.resolved_intents
    claim_ids = {claim.claim_id for claim in result.claims}
    assert "CLAIM-APP-ROLE-NOT-HUMAN-001" in claim_ids
    assert "CLAIM-APP-ROLE-REALIZER-001" in claim_ids


def test_project_rdf_contains_participant_nature_and_role_realization() -> None:
    knowledge = knowledge_base()
    model = OAGraph()
    ok, participant, error = model.add_node(
        "OperationalEntity",
        "Legacy Crossing Controller",
        expects_activity=True,
        nature="existing_technical_system",
        operational_roles=["Level Crossing Manager"],
    )
    assert ok, error

    project = knowledge.project_rdf(model)
    resource = knowledge._project_uri(participant)  # noqa: SLF001 - projection contract test

    assert (resource, OA.hasParticipantNature, OA.ExistingTechnicalSystemNature) in project
    roles = list(project.objects(resource, OA.realizesRole))
    assert len(roles) == 1
    role = roles[0]
    assert (role, RDF.type, OA.OperationalRole) in project
    assert str(project.value(role, OA.name)) == "Level Crossing Manager"


def test_project_rdf_does_not_hide_imported_system_of_interest_flag() -> None:
    knowledge = knowledge_base()
    model = OAGraph()
    ok, participant, error = model.add_node(
        "OperationalEntity",
        "Crossing Control System",
        expects_activity=True,
        nature="existing_technical_system",
    )
    assert ok, error

    # Simulate malformed imported data that bypassed the application write barrier.
    model.graph.nodes[participant]["is_system_of_interest"] = True
    comparison = knowledge.compare_model(model)

    assert not comparison.conforms
    assert any(
        issue.severity == "VIOLATION"
        and "system of interest" in issue.message.casefold()
        for issue in comparison.issues
    )


class BoundaryClassifier(SimplifiedParticipantClassificationMixin):
    def __init__(self, knowledge: ArcadiaKnowledgeBase, choices: list[str]) -> None:
        self.knowledge = knowledge
        self._choices = iter(choices)
        self.notices: list[str] = []
        self.questions: list[str] = []

    def ask_choice(self, question, choices, why, extra_lines=None):
        del choices, why, extra_lines
        self.questions.append(question)
        return next(self._choices)

    def add_notice(self, message: str) -> None:
        self.notices.append(message)


def test_role_realization_question_can_confirm_human_actor() -> None:
    app = BoundaryClassifier(knowledge_base(), ["human"])
    decision = app.confirm_participant_classification("Level Crossing Manager")

    assert decision is not None
    concept, name, attributes = decision
    assert concept == "OperationalActor"
    assert name == "Level Crossing Manager"
    assert attributes["nature"] == "human_individual"
    assert attributes["operational_roles"] == ["Level Crossing Manager"]
    assert attributes["classification_rules"] == ["KG_ROLE_REALIZATION"]
    assert "Who or what performs" in app.questions[0]


def test_role_realization_question_blocks_solution_being_designed() -> None:
    app = BoundaryClassifier(knowledge_base(), ["solution"])
    decision = app.confirm_participant_classification("Level Crossing Controller")

    assert decision is None
    assert app.notices
    assert "kept outside the operational model" in app.notices[-1]


def test_technical_boundary_can_confirm_existing_external_system() -> None:
    app = BoundaryClassifier(knowledge_base(), ["existing"])
    decision = app.confirm_participant_classification("Level Crossing System")

    assert decision is not None
    concept, _, attributes = decision
    assert concept == "OperationalEntity"
    assert attributes["nature"] == "existing_technical_system"
    assert attributes["boundary_status"] == "existing_technical_participant"
    assert attributes["classification_rules"] == ["KG_TECHNICAL_BOUNDARY"]
