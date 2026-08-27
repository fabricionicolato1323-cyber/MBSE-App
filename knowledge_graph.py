from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from rdflib import Dataset, Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS, PROV, XSD
from pyshacl import validate as shacl_validate


OA = Namespace("https://github.com/fabricionicolato1323-cyber/MBSE-App/knowledge/arcadia/oa#")
SH = Namespace("http://www.w3.org/ns/shacl#")

ONTOLOGY_GRAPH = URIRef("urn:graph:ontology")
REFERENCE_GRAPH = URIRef("urn:graph:arcadia-reference")
SHAPES_GRAPH = URIRef("urn:graph:arcadia-shapes")
PROJECT_GRAPH = URIRef("urn:graph:project-approved")
CANDIDATE_GRAPH = URIRef("urn:graph:project-candidates")
VALIDATION_GRAPH = URIRef("urn:graph:validation")
AUDIT_GRAPH = URIRef("urn:graph:audit")

NAMED_GRAPHS = (
    ONTOLOGY_GRAPH,
    REFERENCE_GRAPH,
    SHAPES_GRAPH,
    PROJECT_GRAPH,
    CANDIDATE_GRAPH,
    VALIDATION_GRAPH,
    AUDIT_GRAPH,
)


@dataclass(frozen=True)
class KnowledgeClaim:
    claim_id: str
    text: str
    intents: tuple[str, ...]
    status: str
    source_titles: tuple[str, ...]
    source_urls: tuple[str, ...]
    locator: str
    about_labels: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalResult:
    coverage: str
    claims: tuple[KnowledgeClaim, ...]
    resolved_intents: tuple[str, ...]
    elapsed_ms: float


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    focus_id: str
    focus_name: str
    message: str
    source_shape: str


@dataclass(frozen=True)
class ModelComparison:
    conforms: bool
    issues: tuple[ValidationIssue, ...]
    project_triples: int
    elapsed_ms: float

    def count(self, severity: str) -> int:
        return sum(issue.severity == severity for issue in self.issues)


@dataclass(frozen=True)
class ExportArtifacts:
    json_path: Path
    turtle_path: Path
    validation_report_path: Path
    comparison: ModelComparison


class ArcadiaKnowledgeBase:
    """Arcadia reference dataset plus derived project validation layers.

    NetworkX remains the executable project graph. RDF/OWL, SPARQL and SHACL are
    authority, query, validation and export layers. Candidate statements are kept
    in a named graph that is intentionally separate from the user-approved graph.
    Nothing in this class writes a candidate directly into the NetworkX model.
    """

    _STOPWORDS = {
        "a", "an", "and", "are", "as", "be", "between", "can", "does",
        "for", "from", "how", "in", "is", "it", "of", "on", "or", "should",
        "the", "to", "what", "when", "where", "which", "who", "why", "with",
        "como", "da", "de", "do", "e", "em", "entre", "o", "os", "ou",
        "para", "por", "qual", "que", "um", "uma",
    }

    _INTENT_ALIASES = {
        "define_operational_analysis": (
            "operational analysis", "arcadia oa", "analise operacional",
        ),
        "purpose_of_operational_analysis": (
            "purpose of operational analysis", "why operational analysis",
        ),
        "how_to_start_oa": (
            "start operational analysis", "begin operational analysis",
        ),
        "define_operational_capability": (
            "operational capability", "capacidade operacional",
        ),
        "how_to_describe_capability": (
            "describe capability", "name capability", "capability metric",
        ),
        "define_operational_actor": (
            "operational actor", "ator operacional",
        ),
        "define_operational_entity": (
            "operational entity", "entidade operacional",
        ),
        "define_operational_participant": (
            "participant",
            "operational participant",
            "participante operacional",
        ),
        "define_environmental_participant": (
            "environmental participant", "environmental_participant",
            "participante ambiental",
        ),
        "define_participant_nature": (
            "participant nature", "participant_nature", "classification nature",
        ),
        "actor_vs_entity": (
            "actor and entity", "actor vs entity", "actor versus entity",
            "difference between actor and entity", "ator e entidade",
        ),
        "can_building_be_operational_entity": (
            "building operational entity", "facility operational entity",
        ),
        "can_area_be_operational_entity": (
            "area operational entity", "place operational entity",
        ),
        "define_operational_activity": (
            "operational activity", "atividade operacional",
        ),
        "how_to_name_activity": (
            "name activity", "describe activity", "activity naming",
        ),
        "activity_vs_system_function": (
            "activity and system function", "activity vs function",
        ),
        "define_operational_interaction": (
            "operational interaction", "operational exchange", "interaction",
        ),
        "define_interaction_item": (
            "interaction item", "exchanged item", "exchange content",
        ),
        "define_communication_mean": (
            "communication mean", "communication method",
        ),
        "interaction_vs_communication_mean": (
            "interaction and communication mean",
            "interaction vs communication mean",
        ),
        "define_operational_process": (
            "operational process", "processo operacional",
        ),
        "define_operational_scenario": (
            "operational scenario", "cenario operacional",
        ),
        "process_vs_scenario": (
            "process and scenario", "process vs scenario",
        ),
        "mode_vs_state": (
            "mode and state", "mode vs state", "operational mode",
            "operational state",
        ),
        "what_constraints_in_oa": (
            "operational constraint", "constraints in oa",
        ),
        "system_of_interest_in_oa": (
            "system of interest", "system in operational analysis",
        ),
        "why_no_system_in_oa": (
            "why no system", "exclude system of interest",
        ),
        "how_llm_uses_graph": (
            "llm use knowledge graph", "knowledge graph help",
        ),
        "what_if_graph_has_no_answer": (
            "graph has no answer", "knowledge not found",
        ),
        "who_approves_model": (
            "approve model", "who approves", "user approval",
        ),
    }

    _TYPE_MAP = {
        "OperationalCapability": OA.OperationalCapability,
        "OperationalActor": OA.OperationalActor,
        "OperationalEntity": OA.OperationalEntity,
        "OperationalActivity": OA.OperationalActivity,
    }

    # The curated SHACL package is bilingual in purpose but currently stores its
    # result messages in Portuguese. The terminal application is English-only, so
    # messages are translated at the presentation boundary without changing rules.
    _MESSAGE_TRANSLATIONS = {
        "Todo elemento do Project Graph deve possuir exatamente um identificador textual estável.": "Every Project Graph element must have exactly one stable text identifier.",
        "O elemento ainda não possui nome.": "The element does not have a name yet.",
        "O sistema de interesse não deve ser introduzido como elemento da Análise Operacional; sua contribuição e fronteira são definidas na System Need Analysis.": "The system of interest must not be introduced as an Operational Analysis element; its contribution and boundary are defined in System Need Analysis.",
        "Operational Actor é uma Operational Entity não decomponível.": "An Operational Actor is a non-decomposable Operational Entity.",
        "Um Operational Actor não deve conter outras entidades operacionais.": "An Operational Actor must not contain other operational entities.",
        "A decomposição de entidades contém um ciclo: uma entidade não pode conter a si própria, direta ou indiretamente.": "Entity decomposition contains a cycle: an entity cannot contain itself directly or indirectly.",
        "A entidade está órfã: não realiza atividade, não participa de capacidade, não é conectada por meio de comunicação e não aparece como parte de outra entidade.": "The entity is orphaned: it performs no activity, is involved in no capability, has no communication connection, and is not part of another entity.",
        "A missão não utiliza nenhuma capacidade operacional.": "The mission does not use an operational capability.",
        "A capacidade não está relacionada a nenhuma missão operacional.": "The capability is not related to an operational mission.",
        "A capacidade não possui entidade/ator envolvido.": "The capability has no involved entity or actor.",
        "A capacidade ainda não é descrita por processo ou cenário operacional.": "The capability is not yet described by an operational process or scenario.",
        "A atividade não possui entidade/ator responsável. Registre o performer ou uma lacuna explícita.": "The activity has no responsible entity or actor. Record a performer or an explicit gap.",
        "A decomposição de atividades contém um ciclo.": "Activity decomposition contains a cycle.",
        "A interação deve possuir exatamente uma atividade fonte.": "The interaction must have exactly one source activity.",
        "A interação deve possuir exatamente uma atividade destino.": "The interaction must have exactly one target activity.",
        "A interação não identifica o conteúdo trocado.": "The interaction does not identify the exchanged content.",
        "A interação possui a mesma atividade como fonte e destino; confirme se a autorrelação é intencional.": "The interaction has the same source and target activity; confirm whether the self-relation is intentional.",
        "O item de interação ainda não referencia dados/conceitos do domínio; isso pode limitar análise de conteúdo.": "The interaction item does not yet reference domain data or concepts; this may limit content analysis.",
        "Um meio de comunicação deve conectar pelo menos duas entidades/atores.": "A communication mean must connect at least two entities or actors.",
        "O meio de comunicação não está relacionado a nenhuma interação operacional.": "The communication mean is not related to any operational interaction.",
        "O processo não descreve nenhuma capacidade operacional.": "The process does not describe an operational capability.",
        "O processo possui menos de dois elementos e ainda não representa um caminho operacional significativo.": "The process has fewer than two elements and does not yet represent a meaningful operational path.",
        "O cenário não descreve nenhuma capacidade operacional.": "The scenario does not describe an operational capability.",
        "O cenário ainda não contém uma sequência operacional suficiente.": "The scenario does not yet contain a sufficient operational sequence.",
        "A ocorrência deve referenciar exatamente uma atividade ou interação.": "The occurrence must reference exactly one activity or interaction.",
        "A ocorrência não possui um índice de sequência válido.": "The occurrence does not have a valid sequence index.",
        "A restrição não está aplicada a nenhum elemento operacional.": "The constraint is not applied to an operational element.",
        "O parâmetro dimensionante não possui valor ou critério.": "The dimensioning parameter does not have a value or criterion.",
        "A afirmação de conhecimento não possui texto.": "The knowledge claim does not have assertion text.",
        "A afirmação precisa declarar se é referência Arcadia, recomendação, política ou heurística.": "The claim must state whether it is an Arcadia reference, recommendation, policy, or heuristic.",
        "Uma afirmação marcada como referência Arcadia precisa apontar para uma fonte.": "A claim marked as an Arcadia reference must point to a source.",
    }

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.dataset = Dataset()
        self.ontology = self.dataset.graph(ONTOLOGY_GRAPH)
        self.reference = self.dataset.graph(REFERENCE_GRAPH)
        self.shapes = self.dataset.graph(SHAPES_GRAPH)
        self.project = self.dataset.graph(PROJECT_GRAPH)
        self.candidates = self.dataset.graph(CANDIDATE_GRAPH)
        self.validation = self.dataset.graph(VALIDATION_GRAPH)
        self.audit = self.dataset.graph(AUDIT_GRAPH)

        self.ontology.parse(
            self.base_dir / "02_arcadia_oa_ontology.ttl",
            format="turtle",
        )
        self.reference.parse(
            self.base_dir / "03_arcadia_oa_reference_claims.ttl",
            format="turtle",
        )
        self.shapes.parse(
            self.base_dir / "04_arcadia_oa_shapes.ttl",
            format="turtle",
        )
        self.claims = tuple(self._load_claims())
        if not self.claims:
            raise ValueError("The Arcadia reference graph contains no KnowledgeClaim.")

    @staticmethod
    def _local_name(value: URIRef | str) -> str:
        text = str(value)
        return text.rsplit("#", 1)[-1].rsplit("/", 1)[-1]

    @staticmethod
    def _english_locator(value: str) -> str:
        translated = value
        for source, target in (
            ("seções", "sections"),
            ("seção", "section"),
            (" do PDF", " of the PDF"),
            (" e resposta sobre ", " and answer about "),
            ("Q&A sobre ", "Q&A about "),
        ):
            translated = translated.replace(source, target)
        return translated

    @classmethod
    def _normalize(cls, value: str) -> str:
        folded = unicodedata.normalize("NFKD", value.casefold())
        ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()

    @classmethod
    def _tokens(cls, value: str) -> set[str]:
        return {
            token
            for token in cls._normalize(value).split()
            if len(token) > 1 and token not in cls._STOPWORDS
        }

    def _label(self, resource: URIRef) -> str:
        labels = list(self.ontology.objects(resource, RDFS.label))
        english = next(
            (str(label) for label in labels if getattr(label, "language", None) == "en"),
            None,
        )
        return english or (str(labels[0]) if labels else self._local_name(resource))

    def _load_claims(self) -> list[KnowledgeClaim]:
        claims: list[KnowledgeClaim] = []
        for resource in sorted(
            self.reference.subjects(RDF.type, OA.KnowledgeClaim),
            key=str,
        ):
            claim_id = str(self.reference.value(resource, OA.identifier) or "")
            texts = list(self.reference.objects(resource, OA.assertionText))
            text_value = next(
                (str(value) for value in texts if getattr(value, "language", None) == "en"),
                str(texts[0]) if texts else "",
            )
            intents = tuple(
                sorted(str(value) for value in self.reference.objects(resource, OA.answersIntent))
            )
            status_resource = self.reference.value(resource, OA.guidanceStatus)
            status = self._local_name(status_resource) if status_resource else "Unspecified"
            sources = tuple(self.reference.objects(resource, PROV.wasDerivedFrom))
            source_titles = tuple(
                str(self.reference.value(source, DCTERMS.title) or self._local_name(source))
                for source in sources
            )
            source_urls = tuple(
                str(url)
                for source in sources
                for url in self.reference.objects(source, DCTERMS.source)
            )
            about_labels = tuple(
                self._label(element)
                for element in self.reference.objects(resource, OA.aboutElement)
            )
            claims.append(
                KnowledgeClaim(
                    claim_id=claim_id,
                    text=text_value,
                    intents=intents,
                    status=status,
                    source_titles=source_titles,
                    source_urls=source_urls,
                    locator=str(self.reference.value(resource, OA.sourceLocator) or ""),
                    about_labels=about_labels,
                )
            )
        return claims

    def stats(self) -> dict[str, int]:
        return {
            "ontology_triples": len(self.ontology),
            "reference_triples": len(self.reference),
            "shape_triples": len(self.shapes),
            "project_triples": len(self.project),
            "candidate_triples": len(self.candidates),
            "validation_triples": len(self.validation),
            "audit_triples": len(self.audit),
            "named_graphs": len(NAMED_GRAPHS),
            "claims": len(self.claims),
        }

    @staticmethod
    def named_graph_iris() -> tuple[str, ...]:
        return tuple(str(identifier) for identifier in NAMED_GRAPHS)

    def _resolve_intents(self, question: str) -> tuple[str, ...]:
        normalized = self._normalize(question)
        question_tokens = self._tokens(question)
        matches: list[tuple[int, str]] = []
        for intent, aliases in self._INTENT_ALIASES.items():
            score = 0
            for alias in aliases:
                normalized_alias = self._normalize(alias)
                alias_tokens = self._tokens(alias)
                if normalized_alias and normalized_alias in normalized:
                    score = max(score, 12 + len(alias_tokens))
                elif alias_tokens and alias_tokens <= question_tokens:
                    score = max(score, 8 + len(alias_tokens))
            if score:
                matches.append((score, intent))

        if {"actor", "entity"} <= question_tokens:
            matches.append((20, "actor_vs_entity"))
        if {"process", "scenario"} <= question_tokens:
            matches.append((20, "process_vs_scenario"))
        if {"mode", "state"} <= question_tokens:
            matches.append((20, "mode_vs_state"))
        if {"interaction", "communication"} <= question_tokens:
            matches.append((20, "interaction_vs_communication_mean"))

        if not matches:
            return ()
        best = max(score for score, _ in matches)
        return tuple(sorted({intent for score, intent in matches if score >= best - 1}))

    def retrieve(self, question: str, limit: int = 4) -> RetrievalResult:
        started = time.perf_counter()
        if not question.strip():
            return RetrievalResult("NOT_FOUND", (), (), 0.0)

        resolved = self._resolve_intents(question)
        if resolved:
            direct = [
                claim
                for claim in self.claims
                if set(claim.intents) & set(resolved)
            ]
            if direct:
                elapsed = (time.perf_counter() - started) * 1000
                return RetrievalResult(
                    "SUPPORTED",
                    tuple(direct[:limit]),
                    resolved,
                    elapsed,
                )

        question_tokens = self._tokens(question)
        scored: list[tuple[int, KnowledgeClaim]] = []
        for claim in self.claims:
            searchable = " ".join(
                (*claim.intents, *claim.about_labels, claim.text)
            ).replace("_", " ")
            overlap = question_tokens & self._tokens(searchable)
            if overlap:
                scored.append((len(overlap), claim))

        scored.sort(key=lambda item: (-item[0], item[1].claim_id))
        if not scored:
            coverage = "NOT_FOUND"
            selected: tuple[KnowledgeClaim, ...] = ()
        else:
            top_score = scored[0][0]
            selected = tuple(
                claim for score, claim in scored if score >= max(1, top_score - 1)
            )[:limit]
            coverage = "SUPPORTED" if top_score >= 2 else "PARTIALLY_SUPPORTED"

        elapsed = (time.perf_counter() - started) * 1000
        return RetrievalResult(coverage, selected, resolved, elapsed)

    @staticmethod
    def _evidence_packet(result: RetrievalResult) -> list[dict]:
        return [
            {
                "claim_id": claim.claim_id,
                "text": claim.text,
                "status": claim.status,
                "source": list(claim.source_titles),
                "locator": claim.locator,
            }
            for claim in result.claims
        ]

    @staticmethod
    def _verified_llm_answer(raw: dict, allowed_ids: set[str]) -> tuple[str, tuple[str, ...]] | None:
        if not isinstance(raw, dict) or raw.get("coverage") != "SUPPORTED":
            return None
        answer = str(raw.get("answer") or "").strip()
        citations = raw.get("claim_ids")
        if not answer or not isinstance(citations, list) or not citations:
            return None
        cited = tuple(str(value) for value in citations)
        if set(cited) != allowed_ids or len(cited) != len(set(cited)):
            return None
        if len(answer) > 1800:
            return None
        return answer, cited

    def answer(self, question: str, llm) -> str:
        total_started = time.perf_counter()
        result = self.retrieve(question)
        if not result.claims or result.coverage == "NOT_FOUND":
            total_ms = (time.perf_counter() - total_started) * 1000
            return (
                "Coverage: NOT_FOUND\n\n"
                "The Arcadia knowledge graph does not contain enough evidence to "
                "answer that question. No answer was completed from model memory.\n\n"
                f"Timing: retrieval {result.elapsed_ms:.1f} ms | total {total_ms:.1f} ms"
            )

        llm_started = time.perf_counter()
        try:
            raw = llm.answer_from_knowledge(
                question,
                self._evidence_packet(result),
            )
        except Exception:
            raw = {}
        llm_ms = (time.perf_counter() - llm_started) * 1000
        verified = self._verified_llm_answer(
            raw,
            {claim.claim_id for claim in result.claims},
        )

        lines = [f"Coverage: {result.coverage}", ""]
        if verified is None:
            lines.extend(
                [
                    "A grounded explanation could not be verified, so no unverified "
                    "answer was shown.",
                    "",
                    "Retrieved evidence:",
                ]
            )
            cited_ids = tuple(claim.claim_id for claim in result.claims)
        else:
            answer, cited_ids = verified
            lines.extend([answer, "", "Evidence:"])

        by_id = {claim.claim_id: claim for claim in result.claims}
        for claim_id in cited_ids:
            claim = by_id[claim_id]
            source = "; ".join(claim.source_titles) or "Application-curated policy"
            english_locator = self._english_locator(claim.locator)
            locator = f", {english_locator}" if english_locator else ""
            lines.append(
                f"- {claim.claim_id} [{claim.status}] — {source}{locator}"
            )
            for source_url in claim.source_urls:
                lines.append(f"  Source: {source_url}")

        total_ms = (time.perf_counter() - total_started) * 1000
        lines.extend(
            [
                "",
                (
                    f"Timing: retrieval {result.elapsed_ms:.1f} ms | "
                    f"LLM {llm_ms:.1f} ms | total {total_ms:.1f} ms"
                ),
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _project_uri(identifier: str) -> URIRef:
        return URIRef(f"urn:mbse-app:project:{quote(identifier, safe='')}")

    @staticmethod
    def _synthetic_uri(kind: str, identifier: str) -> URIRef:
        return URIRef(
            f"urn:mbse-app:project:{quote(kind, safe='')}:{quote(identifier, safe='')}"
        )

    def _record_audit(self, action: str, detail: str) -> None:
        event = URIRef(f"urn:mbse-app:audit:{uuid4()}")
        self.audit.add((event, RDF.type, PROV.Activity))
        self.audit.add((event, DCTERMS.type, Literal(action)))
        self.audit.add((event, DCTERMS.description, Literal(detail)))
        self.audit.add(
            (
                event,
                PROV.generatedAtTime,
                Literal(datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime),
            )
        )

    def stage_candidate(
        self,
        candidate_id: str,
        suggested_type: str,
        name: str,
        *,
        evidence: str = "",
        source: str = "assistant",
    ) -> URIRef:
        """Store an unapproved extraction only in the candidate named graph."""
        candidate_id = str(candidate_id).strip()
        if not candidate_id:
            raise ValueError("Candidate ID is required.")
        resource = URIRef(f"urn:mbse-app:candidate:{quote(candidate_id, safe='')}")
        self.candidates.remove((resource, None, None))
        self.candidates.add((resource, RDF.type, OA.CandidateMention))
        self.candidates.add((resource, OA.identifier, Literal(candidate_id)))
        self.candidates.add((resource, OA.name, Literal(str(name))))
        self.candidates.add((resource, OA.suggestedType, Literal(str(suggested_type))))
        self.candidates.add((resource, DCTERMS.source, Literal(str(source))))
        if evidence:
            self.candidates.add((resource, OA.evidenceText, Literal(str(evidence))))
        self._record_audit("candidate_staged", candidate_id)
        return resource

    def discard_candidate(self, candidate_id: str) -> bool:
        resource = URIRef(f"urn:mbse-app:candidate:{quote(str(candidate_id), safe='')}")
        existed = any(self.candidates.triples((resource, None, None)))
        self.candidates.remove((resource, None, None))
        if existed:
            self._record_audit("candidate_discarded", str(candidate_id))
        return existed

    def candidate_count(self) -> int:
        return len(set(self.candidates.subjects(RDF.type, OA.CandidateMention)))

    def project_rdf(self, model) -> Graph:
        project = Graph(identifier=PROJECT_GRAPH)
        project.bind("oa", OA)
        node_uris: dict[str, URIRef] = {}

        for node_id, data in model.graph.nodes(data=True):
            node_type = str(data.get("type", ""))
            rdf_type = self._TYPE_MAP.get(node_type)
            if rdf_type is None:
                continue
            identifier = str(data.get("uuid") or node_id)
            resource = self._project_uri(identifier)
            node_uris[node_id] = resource
            project.add((resource, RDF.type, OA.ProjectElement))
            project.add((resource, RDF.type, rdf_type))
            if node_type == "OperationalActor":
                project.add((resource, RDF.type, OA.OperationalEntity))
                project.add((resource, OA.isDecomposable, Literal(False)))
            project.add((resource, OA.identifier, Literal(identifier)))
            project.add((resource, OA.name, Literal(str(data.get("name", node_id)))))
            project.add((resource, OA.isSystemOfInterest, Literal(False)))
            if data.get("sid"):
                project.add((resource, DCTERMS.identifier, Literal(str(data["sid"]))))

        interactions: list[tuple[URIRef, str, str]] = []
        communication_edges: list[tuple[URIRef, str, str]] = []

        for index, (source, target, key, data) in enumerate(
            model.graph.edges(keys=True, data=True),
            start=1,
        ):
            if source not in node_uris or target not in node_uris:
                continue
            relation = data.get("type")
            source_uri = node_uris[source]
            target_uri = node_uris[target]
            edge_id = str(data.get("uuid") or f"legacy-edge-{index}")
            if relation == "PERFORMS":
                project.add((source_uri, OA.performsActivity, target_uri))
                project.add((target_uri, OA.performedBy, source_uri))
            elif relation == "CONTAINS":
                project.add((source_uri, OA.containsEntity, target_uri))
            elif relation == "SUPPORTS_CAPABILITY":
                for performer in model.participants_for_activity(source):
                    performer_uri = node_uris.get(performer)
                    if performer_uri:
                        project.add((performer_uri, OA.involvedInCapability, target_uri))
                        project.add((target_uri, OA.hasInvolvedEntity, performer_uri))
            elif relation == "OPERATIONAL_EXCHANGE":
                interaction = self._synthetic_uri("interaction", edge_id)
                item = self._synthetic_uri("interaction-item", edge_id)
                name = str(data.get("name") or "Operational exchange")
                for resource, rdf_type, identifier, item_name in (
                    (interaction, OA.OperationalInteraction, edge_id, name),
                    (item, OA.InteractionItem, f"{edge_id}:item", name),
                ):
                    project.add((resource, RDF.type, OA.ProjectElement))
                    project.add((resource, RDF.type, rdf_type))
                    project.add((resource, OA.identifier, Literal(identifier)))
                    project.add((resource, OA.name, Literal(item_name)))
                    project.add((resource, OA.isSystemOfInterest, Literal(False)))
                project.add((interaction, OA.sourceActivity, source_uri))
                project.add((interaction, OA.targetActivity, target_uri))
                project.add((interaction, OA.conveys, item))
                interactions.append((interaction, source, target))
            elif relation == "COMMUNICATION_MEAN":
                mean = self._synthetic_uri("communication-mean", edge_id)
                name = str(data.get("name") or "Communication mean")
                project.add((mean, RDF.type, OA.ProjectElement))
                project.add((mean, RDF.type, OA.CommunicationMean))
                project.add((mean, OA.identifier, Literal(edge_id)))
                project.add((mean, OA.name, Literal(name)))
                project.add((mean, OA.isSystemOfInterest, Literal(False)))
                project.add((mean, OA.connectsEntity, source_uri))
                project.add((mean, OA.connectsEntity, target_uri))
                communication_edges.append((mean, source, target))

        for mean, first, second in communication_edges:
            pair = {first, second}
            for interaction, source_activity, target_activity in interactions:
                source_performers = set(model.participants_for_activity(source_activity))
                target_performers = set(model.participants_for_activity(target_activity))
                if any(
                    {source_performer, target_performer} == pair
                    for source_performer in source_performers
                    for target_performer in target_performers
                ):
                    project.add((mean, OA.supportsInteraction, interaction))

        return project

    @staticmethod
    def _replace_graph(target: Graph, source: Graph) -> None:
        target.remove((None, None, None))
        for triple in source:
            target.add(triple)

    def compare_model(self, model) -> ModelComparison:
        started = time.perf_counter()
        project = self.project_rdf(model)
        conforms, report_graph, _ = shacl_validate(
            data_graph=project,
            shacl_graph=self.shapes,
            ont_graph=self.ontology,
            inference="rdfs",
            advanced=True,
            allow_warnings=True,
            allow_infos=True,
        )

        self._replace_graph(self.project, project)
        self._replace_graph(self.validation, report_graph)
        self._record_audit(
            "model_validated",
            f"conforms={bool(conforms)} project_triples={len(project)}",
        )

        issues: list[ValidationIssue] = []
        for result in report_graph.subjects(RDF.type, SH.ValidationResult):
            focus = report_graph.value(result, SH.focusNode)
            severity_uri = report_graph.value(result, SH.resultSeverity)
            raw_message = str(report_graph.value(result, SH.resultMessage) or "Model issue")
            message = self._MESSAGE_TRANSLATIONS.get(raw_message, raw_message)
            shape = report_graph.value(result, SH.sourceShape)
            severity = self._local_name(severity_uri or SH.Info).upper()
            focus_id = str(project.value(focus, OA.identifier) or self._local_name(focus or ""))
            focus_name = str(project.value(focus, OA.name) or focus_id)
            issues.append(
                ValidationIssue(
                    severity=severity,
                    focus_id=focus_id,
                    focus_name=focus_name,
                    message=message,
                    source_shape=self._local_name(shape or ""),
                )
            )

        order = {"VIOLATION": 0, "WARNING": 1, "INFO": 2}
        issues.sort(
            key=lambda issue: (
                order.get(issue.severity, 3),
                issue.focus_name.casefold(),
                issue.message,
            )
        )
        elapsed = (time.perf_counter() - started) * 1000
        return ModelComparison(bool(conforms), tuple(issues), len(project), elapsed)

    @staticmethod
    def format_comparison(comparison: ModelComparison, max_issues: int | None = None) -> str:
        lines = [
            f"Mandatory Arcadia rules: {'PASS' if comparison.conforms else 'FAIL'}",
            (
                f"Issues: {comparison.count('VIOLATION')} violation(s), "
                f"{comparison.count('WARNING')} warning(s), "
                f"{comparison.count('INFO')} information item(s)"
            ),
            f"Project RDF: {comparison.project_triples} triples",
        ]
        selected = comparison.issues
        if max_issues is not None:
            selected = selected[:max_issues]
        if selected:
            lines.append("")
            for issue in selected:
                lines.append(
                    f"- [{issue.severity}] {issue.focus_name} ({issue.focus_id}): "
                    f"{issue.message}"
                )
        if max_issues is not None and len(comparison.issues) > max_issues:
            lines.append(
                f"- ... {len(comparison.issues) - max_issues} more issue(s); "
                "use /compare to see all."
            )
        lines.extend(["", f"Elapsed comparison time: {comparison.elapsed_ms:.1f} ms"])
        return "\n".join(lines)

    @staticmethod
    def _write_text_atomic(path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
        return path

    def validation_report_markdown(self, comparison: ModelComparison) -> str:
        lines = [
            "# OA Validation Report",
            "",
            f"- Mandatory Arcadia rules: {'PASS' if comparison.conforms else 'FAIL'}",
            f"- Violations: {comparison.count('VIOLATION')}",
            f"- Warnings: {comparison.count('WARNING')}",
            f"- Information items: {comparison.count('INFO')}",
            f"- Approved project RDF triples: {comparison.project_triples}",
            f"- Validation elapsed time: {comparison.elapsed_ms:.1f} ms",
            "",
            "## Findings",
            "",
        ]
        if not comparison.issues:
            lines.append("No SHACL findings were produced.")
        else:
            for issue in comparison.issues:
                lines.append(
                    f"- **{issue.severity}** — {issue.focus_name} "
                    f"(`{issue.focus_id}`): {issue.message} "
                    f"_Rule: {issue.source_shape or 'unspecified'}_"
                )
        lines.extend(
            [
                "",
                "Candidate statements are excluded from this report and from the approved RDF export.",
                "",
            ]
        )
        return "\n".join(lines)

    def export_approved_model(
        self,
        model,
        output_dir: str | Path,
    ) -> ExportArtifacts:
        """Export canonical JSON, approved Turtle and a SHACL Markdown report."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = model.save(output_dir / "oa_model.json")
        comparison = self.compare_model(model)
        turtle_path = output_dir / "oa_project_approved.ttl"
        turtle_text = self.project.serialize(format="turtle")
        self._write_text_atomic(turtle_path, str(turtle_text))
        validation_path = output_dir / "oa_validation_report.md"
        self._write_text_atomic(
            validation_path,
            self.validation_report_markdown(comparison),
        )
        self._record_audit(
            "model_exported",
            f"json={json_path.name} turtle={turtle_path.name} report={validation_path.name}",
        )
        return ExportArtifacts(
            json_path=json_path,
            turtle_path=turtle_path,
            validation_report_path=validation_path,
            comparison=comparison,
        )
