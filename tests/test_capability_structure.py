from __future__ import annotations

import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from knowledge_graph import ArcadiaKnowledgeBase, OA
from knowledge_graph_structural_input import install_structural_input_knowledge_support


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE = ROOT / "knowledge_base"


def _knowledge() -> ArcadiaKnowledgeBase:
    install_structural_input_knowledge_support()
    return ArcadiaKnowledgeBase(KNOWLEDGE_BASE)


def test_coordinated_verbs_become_separate_capability_candidates():
    analysis = _knowledge().analyze_capability_statement(
        "Detect and destroy hostile targets."
    )

    assert tuple(item.casefold() for item in analysis.predicate_texts) == (
        "detect",
        "destroy",
    )
    assert tuple(item.casefold() for item in analysis.capability_candidates) == (
        "detect hostile targets",
        "destroy hostile targets",
    )
    assert not analysis.requires_simplification


def test_one_verb_with_coordinated_objects_remains_one_capability():
    analysis = _knowledge().analyze_capability_statement(
        "Detect targets and objects."
    )

    assert tuple(item.casefold() for item in analysis.predicate_texts) == ("detect",)
    assert len(analysis.capability_candidates) == 1
    assert {item.text.casefold() for item in analysis.mentions} >= {
        "targets",
        "objects",
    }


def test_two_predicates_keep_their_own_direct_object_mentions():
    analysis = _knowledge().analyze_capability_statement(
        "Detect targets and warn observers."
    )

    assert tuple(item.casefold() for item in analysis.capability_candidates) == (
        "detect targets",
        "warn observers",
    )
    assert {item.text.casefold() for item in analysis.mentions} >= {
        "targets",
        "observers",
    }


def test_structural_mentions_cover_coordinated_modifiers_and_context_phrase():
    analysis = _knowledge().analyze_capability_statement(
        "Ensure safe vehicles and pedestrians passage through the crossing area."
    )

    mentions = {item.text.casefold(): item.source for item in analysis.mentions}
    assert "vehicles" in mentions
    assert "pedestrians" in mentions
    assert "crossing area" in mentions
    assert mentions["vehicles"] == "coordinated_modifier_structure"
    assert mentions["crossing area"] == "prepositional_structure"


def test_configured_token_limit_requests_simplification():
    text = "Detect " + " ".join(f"item{index}" for index in range(45))
    analysis = _knowledge().analyze_capability_statement(text)
    assert analysis.requires_simplification
    assert analysis.confidence == "low"


def test_external_rdf_lexeme_is_loaded_as_data_without_python_change():
    extension = """
@prefix oa: <https://github.com/fabricionicolato1323-cyber/MBSE-App/knowledge/arcadia/oa#> .

oa:ExternalLexeme a oa:ParticipantLexeme ;
    oa:lexicalForm "widgets" ;
    oa:suggestedConcept "OperationalEntity" ;
    oa:suggestedNature "existing_technical_system" .
""".strip()

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "extension.ttl"
        path.write_text(extension, encoding="utf-8")
        with patch.dict(
            os.environ,
            {"MBSE_STRUCTURAL_KG_EXTENSIONS_PATH": str(path)},
            clear=False,
        ):
            knowledge = _knowledge()
            analysis = knowledge.analyze_capability_statement(
                "Ensure availability around widgets."
            )

    mention = next(item for item in analysis.mentions if item.text.casefold() == "widgets")
    assert mention.source == "lexical_knowledge"
    assert mention.suggested_concept == "OperationalEntity"
    assert mention.suggested_nature == "existing_technical_system"


def test_analysis_is_materialized_only_in_transient_kg_graph():
    knowledge = _knowledge()
    knowledge.analyze_capability_statement("Detect targets.")

    transient = knowledge.last_structural_analysis
    assert any(transient.subjects(predicate=None, object=OA.StructuralAnalysis)) is False
    assert any(transient.subjects(None, OA.StructuralAnalysis)) is False
    assert any(transient.subjects())
    assert len(transient) > 0


def test_new_production_feature_contains_no_application_specific_vocabulary():
    production_paths = [
        ROOT / "capability_structure.py",
        ROOT / "capability_flow.py",
        ROOT / "knowledge_graph_structural_input.py",
        KNOWLEDGE_BASE / "09_structural_input_ontology.ttl",
        KNOWLEDGE_BASE / "10_structural_language_lexicon.ttl",
    ]
    forbidden = (
        r"\btrain\b",
        r"\bcar\b",
        r"\bpedestrian\b",
        r"\bdrone\b",
        r"level\s+crossing",
    )

    for path in production_paths:
        content = path.read_text(encoding="utf-8").casefold()
        for pattern in forbidden:
            assert re.search(pattern, content) is None, f"{pattern} found in {path.name}"
