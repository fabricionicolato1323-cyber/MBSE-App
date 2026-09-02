from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rdflib import Literal, RDF

from knowledge_graph import ArcadiaKnowledgeBase, OA


@dataclass(frozen=True)
class ParticipantBoundaryAssessment:
    """Read-only semantic assessment derived from Knowledge Graph cues."""

    kind: str
    requires_clarification: bool
    suggested_concept: str | None
    suggested_nature: str
    reason: str
    rule_id: str
    matched_cues: tuple[str, ...] = ()


_EXTENSION_FILES = (
    ("ontology", "06_role_boundary_ontology.ttl"),
    ("reference", "07_role_boundary_claims.ttl"),
    ("shapes", "08_role_boundary_shapes.ttl"),
)

_NATURE_MAP = {
    "human_individual": OA.HumanIndividual,
    "organization": OA.OrganizationNature,
    "organizational_unit": OA.OrganizationalUnitNature,
    "team_or_collective": OA.TeamOrCollective,
    "existing_technical_system": OA.ExistingTechnicalSystemNature,
    "infrastructure_or_facility": OA.InfrastructureOrFacilityNature,
    "external_operational_service": OA.ExternalOperationalServiceNature,
    "population_or_community": OA.PopulationOrCommunityNature,
    "environmental_participant": OA.EnvironmentalParticipant,
    "unspecified": OA.UnspecifiedParticipantNature,
}

_INTENT_EXTENSIONS = {
    "role_vs_realizer": (
        "role and realizer",
        "role vs realizer",
        "who performs this role",
        "who realizes this role",
    ),
    "controller_human_or_system": (
        "controller person or system",
        "controller human or system",
        "manager person or system",
        "operator person or system",
    ),
    "technical_participant_vs_soi": (
        "technical participant and system of interest",
        "existing system or system of interest",
        "external system or solution",
        "technical participant vs soi",
    ),
}

_MESSAGE_EXTENSIONS = {
    "O papel operacional ainda não possui um participante real que o realize.": (
        "The operational role does not yet have a real participant that realizes it."
    ),
    "O candidato ainda precisa esclarecer quem ou o que realiza o papel antes da persistência.": (
        "The candidate still needs clarification about who or what realizes the role before persistence."
    ),
    "O candidato foi identificado como a solução em definição e não deve ser persistido como participante da Análise Operacional.": (
        "The candidate was identified as the solution being defined and must not be persisted as an Operational Analysis participant."
    ),
    "Um participante técnico marcado como sistema de interesse não pertence à Análise Operacional; confirme se ele é realmente externo/existente ou se é a solução em definição.": (
        "A technical participant marked as the system of interest does not belong in Operational Analysis; confirm whether it is truly external/existing or the solution being defined."
    ),
}


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def _cue_forms(knowledge: ArcadiaKnowledgeBase, cue_type) -> tuple[str, ...]:
    values: set[str] = set()
    for resource in knowledge.ontology.subjects(RDF.type, cue_type):
        for lexical_form in knowledge.ontology.objects(resource, OA.lexicalForm):
            normalized = knowledge._normalize(str(lexical_form))  # noqa: SLF001 - KG extension
            if normalized:
                values.add(normalized)
    return tuple(sorted(values, key=lambda item: (-len(item), item)))


def _matching_cues(
    knowledge: ArcadiaKnowledgeBase,
    value: str,
    cue_type,
) -> tuple[str, ...]:
    normalized = knowledge._normalize(value)  # noqa: SLF001 - KG extension
    padded = f" {normalized} "
    return tuple(
        cue
        for cue in _cue_forms(knowledge, cue_type)
        if f" {cue} " in padded
    )


def _assess_participant_phrase(
    self: ArcadiaKnowledgeBase,
    value: str,
) -> ParticipantBoundaryAssessment:
    solution = _matching_cues(self, value, OA.SolutionCue)
    role_like = _matching_cues(self, value, OA.RoleLikeCue)
    technical = _matching_cues(self, value, OA.TechnicalCue)
    existing = _matching_cues(self, value, OA.ExistingTechnicalCue)

    if solution:
        return ParticipantBoundaryAssessment(
            kind="solution_boundary",
            requires_clarification=True,
            suggested_concept=None,
            suggested_nature="unspecified",
            reason=(
                "The Knowledge Graph found wording associated with the solution being "
                "defined. Confirm the operational boundary before anything is persisted."
            ),
            rule_id="KG_SOLUTION_BOUNDARY",
            matched_cues=solution,
        )

    if role_like:
        return ParticipantBoundaryAssessment(
            kind="role_realization",
            requires_clarification=True,
            suggested_concept=None,
            suggested_nature="unspecified",
            reason=(
                "The Knowledge Graph treats role-like wording as a responsibility label, "
                "not as proof that the realizer is human."
            ),
            rule_id="KG_ROLE_REALIZATION",
            matched_cues=role_like,
        )

    if technical and existing:
        return ParticipantBoundaryAssessment(
            kind="existing_technical",
            requires_clarification=False,
            suggested_concept="OperationalEntity",
            suggested_nature="existing_technical_system",
            reason=(
                "The wording explicitly identifies an existing/external technical "
                "participant in the operational environment."
            ),
            rule_id="KG_EXISTING_TECHNICAL",
            matched_cues=tuple(dict.fromkeys((*technical, *existing))),
        )

    if technical:
        return ParticipantBoundaryAssessment(
            kind="technical_boundary",
            requires_clarification=True,
            suggested_concept=None,
            suggested_nature="existing_technical_system",
            reason=(
                "A technical element may be a valid existing participant or the solution "
                "being designed; the Knowledge Graph requires that boundary to be clarified."
            ),
            rule_id="KG_TECHNICAL_BOUNDARY",
            matched_cues=technical,
        )

    return ParticipantBoundaryAssessment(
        kind="neutral",
        requires_clarification=False,
        suggested_concept=None,
        suggested_nature="unspecified",
        reason="No role/system boundary cue was found in the Knowledge Graph.",
        rule_id="KG_NO_BOUNDARY_CUE",
    )


def install_role_boundary_knowledge_support() -> None:
    """Extend the shared Knowledge Graph without changing its base package files."""

    cls = ArcadiaKnowledgeBase
    if getattr(cls, "_role_boundary_support_installed", False):
        return

    base_init = cls.__init__
    base_project_rdf = cls.project_rdf

    def extended_init(self, base_dir: str | Path) -> None:
        base_init(self, base_dir)
        root = Path(base_dir)
        for graph_name, filename in _EXTENSION_FILES:
            path = root / filename
            if not path.exists():
                continue
            getattr(self, graph_name).parse(path, format="turtle")

        # The base constructor loads claims before extension files are parsed.
        # Rebuild the immutable evidence index after adding the role-boundary claims.
        self.claims = tuple(self._load_claims())  # noqa: SLF001 - controlled extension

    def extended_project_rdf(self, model):
        project = base_project_rdf(self, model)

        for node_id, data in model.graph.nodes(data=True):
            node_type = str(data.get("type", ""))
            if node_type not in self._TYPE_MAP:  # noqa: SLF001 - shared projection contract
                continue
            resource = self._project_uri(node_id)  # noqa: SLF001

            # Do not hide malformed/imported System-of-Interest flags. The SHACL
            # layer must be able to see and reject them instead of receiving a
            # hard-coded false value from the projection.
            project.remove((resource, OA.isSystemOfInterest, None))
            system_flag = data.get(
                "is_system_of_interest",
                data.get("isSystemOfInterest", False),
            )
            project.add((resource, OA.isSystemOfInterest, Literal(_truthy(system_flag))))

            nature = str(data.get("nature", "unspecified"))
            nature_resource = _NATURE_MAP.get(nature)
            if nature_resource is not None and node_type in {
                "OperationalActor",
                "OperationalEntity",
            }:
                project.add((resource, OA.hasParticipantNature, nature_resource))

            roles = data.get("operational_roles", [])
            if isinstance(roles, str):
                roles = [roles]
            if not isinstance(roles, (list, tuple, set)):
                roles = []

            for index, raw_role in enumerate(roles, start=1):
                role_name = str(raw_role).strip()
                if not role_name:
                    continue
                role_id = f"role:{node_id}:{index}:{role_name}"
                role = self._project_uri(role_id)  # noqa: SLF001
                project.add((role, RDF.type, OA.ProjectElement))
                project.add((role, RDF.type, OA.OperationalRole))
                project.add((role, OA.identifier, Literal(role_id)))
                project.add((role, OA.name, Literal(role_name)))
                project.add((role, OA.isSystemOfInterest, Literal(False)))
                project.add((resource, OA.realizesRole, role))

        return project

    cls.__init__ = extended_init
    cls.project_rdf = extended_project_rdf
    cls.assess_participant_phrase = _assess_participant_phrase
    cls._INTENT_ALIASES.update(_INTENT_EXTENSIONS)
    cls._MESSAGE_TRANSLATIONS.update(_MESSAGE_EXTENSIONS)
    cls._role_boundary_support_installed = True
