from __future__ import annotations

import hashlib
import os
from pathlib import Path

from rdflib import Graph, Literal, RDF, URIRef

from capability_structure import (
    CapabilityStructuralAnalysis,
    ParticipantLexeme,
    StructuralLexicon,
    StructuralPolicy,
    analyze_capability_structure,
)
from knowledge_graph import ArcadiaKnowledgeBase, OA


_EXTENSION_FILES = (
    "09_structural_input_ontology.ttl",
    "10_structural_language_lexicon.ttl",
)
_EXTENSION_ENV = "MBSE_STRUCTURAL_KG_EXTENSIONS_PATH"


def _literal_text(graph, subject, predicate, default: str = "") -> str:
    value = next(iter(graph.objects(subject, predicate)), None)
    return str(value).strip() if value is not None else default


def _literal_int(graph, subject, predicate, default: int) -> int:
    value = next(iter(graph.objects(subject, predicate)), None)
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _cue_forms(knowledge: ArcadiaKnowledgeBase, cue_type) -> frozenset[str]:
    values: set[str] = set()
    for resource in knowledge.ontology.subjects(RDF.type, cue_type):
        for lexical_form in knowledge.ontology.objects(resource, OA.lexicalForm):
            normalized = knowledge._normalize(str(lexical_form))  # noqa: SLF001 - KG extension
            if normalized:
                values.add(normalized)
    return frozenset(values)


def _policy(knowledge: ArcadiaKnowledgeBase) -> StructuralPolicy:
    resource = next(
        iter(knowledge.ontology.subjects(RDF.type, OA.StructuralPolicy)),
        None,
    )
    if resource is None:
        return StructuralPolicy()
    return StructuralPolicy(
        max_accepted_tokens=_literal_int(
            knowledge.ontology,
            resource,
            OA.maxAcceptedTokens,
            40,
        ),
        max_candidate_predicates=_literal_int(
            knowledge.ontology,
            resource,
            OA.maxCandidatePredicates,
            4,
        ),
        max_complexity_score=_literal_int(
            knowledge.ontology,
            resource,
            OA.maxComplexityScore,
            5,
        ),
    )


def _participant_lexemes(
    knowledge: ArcadiaKnowledgeBase,
) -> tuple[ParticipantLexeme, ...]:
    result: list[ParticipantLexeme] = []
    seen: set[str] = set()
    for resource in knowledge.ontology.subjects(RDF.type, OA.ParticipantLexeme):
        lexical_form = _literal_text(
            knowledge.ontology,
            resource,
            OA.lexicalForm,
        )
        normalized = knowledge._normalize(lexical_form)  # noqa: SLF001 - KG extension
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        concept = _literal_text(
            knowledge.ontology,
            resource,
            OA.suggestedConcept,
        ) or None
        nature = _literal_text(
            knowledge.ontology,
            resource,
            OA.suggestedNature,
            "unspecified",
        )
        result.append(
            ParticipantLexeme(
                lexical_form=lexical_form,
                suggested_concept=concept,
                suggested_nature=nature,
            )
        )
    return tuple(result)


def _structural_lexicon(knowledge: ArcadiaKnowledgeBase) -> StructuralLexicon:
    return StructuralLexicon(
        predicates=_cue_forms(knowledge, OA.PredicateCue),
        coordinators=_cue_forms(knowledge, OA.CoordinatorCue),
        mention_prepositions=_cue_forms(knowledge, OA.MentionPrepositionCue),
        clause_markers=_cue_forms(knowledge, OA.ClauseMarkerCue),
        determiners=_cue_forms(knowledge, OA.DeterminerCue),
        qualifiers=_cue_forms(knowledge, OA.QualifierCue),
        outcome_nouns=_cue_forms(knowledge, OA.OutcomeNounCue),
        participant_lexemes=_participant_lexemes(knowledge),
        policy=_policy(knowledge),
    )


def _analysis_graph(analysis: CapabilityStructuralAnalysis) -> Graph:
    graph = Graph()
    digest = hashlib.sha1(
        analysis.normalized_text.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:16]
    root = URIRef(f"urn:structural-analysis:{digest}")
    graph.add((root, RDF.type, OA.StructuralAnalysis))
    graph.add((root, OA.sourceText, Literal(analysis.normalized_text)))
    graph.add((root, OA.complexityScore, Literal(analysis.complexity_score)))
    graph.add((root, OA.requiresSimplification, Literal(analysis.requires_simplification)))
    graph.add((root, OA.analysisConfidence, Literal(analysis.confidence)))

    for index, candidate in enumerate(analysis.capability_candidates, start=1):
        resource = URIRef(f"{root}:predicate:{index}")
        graph.add((resource, RDF.type, OA.PredicateCandidate))
        graph.add((resource, OA.predicateIndex, Literal(index)))
        graph.add((resource, OA.candidateText, Literal(candidate)))
        graph.add((root, OA.hasPredicate, resource))

    for index, mention in enumerate(analysis.mentions, start=1):
        resource = URIRef(f"{root}:mention:{index}")
        graph.add((resource, RDF.type, OA.MentionCandidate))
        graph.add((resource, OA.candidateText, Literal(mention.text)))
        graph.add((resource, OA.mentionSource, Literal(mention.source)))
        if mention.suggested_concept:
            graph.add((resource, OA.suggestedConcept, Literal(mention.suggested_concept)))
        if mention.suggested_nature:
            graph.add((resource, OA.suggestedNature, Literal(mention.suggested_nature)))
        graph.add((root, OA.hasMention, resource))

    return graph


def _external_paths() -> tuple[Path, ...]:
    raw = os.getenv(_EXTENSION_ENV, "").strip()
    if not raw:
        return ()
    return tuple(
        Path(item).expanduser()
        for item in raw.split(os.pathsep)
        if item.strip()
    )


def install_structural_input_knowledge_support() -> None:
    """Add structural input analysis to the shared read-only Knowledge Graph.

    Structural grammar and thresholds are loaded as RDF data. Optional lexical or
    domain knowledge can be supplied through MBSE_STRUCTURAL_KG_EXTENSIONS_PATH.
    No application-specific vocabulary is embedded in Python.
    """

    cls = ArcadiaKnowledgeBase
    if getattr(cls, "_structural_input_support_installed", False):
        return

    base_init = cls.__init__

    def extended_init(self, base_dir: str | Path) -> None:
        base_init(self, base_dir)
        root = Path(base_dir)
        for filename in _EXTENSION_FILES:
            path = root / filename
            if path.exists():
                self.ontology.parse(path, format="turtle")
        for path in _external_paths():
            if not path.exists():
                raise FileNotFoundError(
                    f"Structural KG extension does not exist: {path}"
                )
            self.ontology.parse(path, format="turtle")

    def analyze_capability_statement(
        self,
        value: str,
    ) -> CapabilityStructuralAnalysis:
        analysis = analyze_capability_structure(
            value,
            _structural_lexicon(self),
        )
        # Keep the transient analysis available for diagnostics/tests without ever
        # merging it into the approved Project Graph or NetworkX model.
        self.last_structural_analysis = _analysis_graph(analysis)
        return analysis

    cls.__init__ = extended_init
    cls.analyze_capability_statement = analyze_capability_statement
    cls._structural_input_support_installed = True
