from __future__ import annotations

import time
from collections import defaultdict

import networkx as nx
from pyshacl import validate as shacl_validate
from rdflib import Graph, RDF

from knowledge_graph import OA, SH, ModelComparison, ValidationIssue


CAPABILITY_DECOMPOSITION = OA.decomposesCapability

_SUPPLEMENTAL_SHAPES = r'''@prefix oa: <https://github.com/fabricionicolato1323-cyber/MBSE-App/knowledge/arcadia/oa#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .

oa:Feature5CapabilityDecompositionShape
    a sh:NodeShape ;
    sh:targetClass oa:OperationalCapability ;
    sh:property [
        sh:path [ sh:inversePath oa:decomposesCapability ] ;
        sh:maxCount 1 ;
        sh:severity sh:Violation ;
        sh:message "A goal cannot belong to more than one decomposition parent."
    ] ;
    sh:sparql [
        a sh:SPARQLConstraint ;
        sh:severity sh:Violation ;
        sh:message "Goal decomposition contains a cycle." ;
        sh:select """
            PREFIX oa: <https://github.com/fabricionicolato1323-cyber/MBSE-App/knowledge/arcadia/oa#>
            SELECT $this WHERE { $this oa:decomposesCapability+ $this . }
        """
    ] .

oa:Feature5ActivityDecompositionShape
    a sh:NodeShape ;
    sh:targetClass oa:OperationalActivity ;
    sh:property [
        sh:path [ sh:inversePath oa:containsActivity ] ;
        sh:maxCount 1 ;
        sh:severity sh:Violation ;
        sh:message "An action cannot belong to more than one decomposition parent."
    ] ;
    sh:sparql [
        a sh:SPARQLConstraint ;
        sh:severity sh:Violation ;
        sh:message "Action decomposition contains a cycle." ;
        sh:select """
            PREFIX oa: <https://github.com/fabricionicolato1323-cyber/MBSE-App/knowledge/arcadia/oa#>
            SELECT $this WHERE { $this oa:containsActivity+ $this . }
        """
    ] .

oa:Feature5EntityCompositionShape
    a sh:NodeShape ;
    sh:targetClass oa:OperationalEntity ;
    sh:property [
        sh:path [ sh:inversePath oa:containsEntity ] ;
        sh:maxCount 1 ;
        sh:severity sh:Violation ;
        sh:message "A participant/context item cannot belong to more than one structural parent."
    ] .
'''


def _node_type(model, node_id: str) -> str:
    if node_id not in model.graph:
        return ""
    return str(model.graph.nodes[node_id].get("type", ""))


def _node_name(model, node_id: str) -> str:
    try:
        return model.name(node_id)
    except Exception:
        return str(node_id)


def _issue(model, node_id: str, message: str) -> ValidationIssue:
    return ValidationIssue(
        severity="VIOLATION",
        focus_id=str(node_id),
        focus_name=_node_name(model, node_id),
        message=message,
        source_shape="Feature5ModelIntegrity",
    )


def structural_issues(model) -> list[ValidationIssue]:
    """Validate persisted graph structure, including graphs loaded outside write barriers."""
    issues: list[ValidationIssue] = []
    parents: dict[tuple[str, str], list[str]] = defaultdict(list)
    goal_graph = nx.DiGraph()
    action_graph = nx.DiGraph()
    entity_graph = nx.DiGraph()

    for source, target, data in model.graph.edges(data=True):
        relation = str(data.get("type", ""))
        source_type = _node_type(model, source)
        target_type = _node_type(model, target)

        if relation == "DECOMPOSES":
            if source_type == target_type == "OperationalCapability":
                goal_graph.add_edge(source, target)
                parents[(target, "goal")].append(source)
            elif source_type == target_type == "OperationalActivity":
                action_graph.add_edge(source, target)
                parents[(target, "action")].append(source)
            else:
                issues.append(
                    _issue(
                        model,
                        source,
                        "DECOMPOSES must connect goals to goals or actions to actions.",
                    )
                )

        elif relation == "CONTAINS":
            valid_target = target_type in {"OperationalEntity", "OperationalActor"}
            if source_type != "OperationalEntity" or not valid_target:
                issues.append(
                    _issue(
                        model,
                        source,
                        "CONTAINS must connect a participant/context group to a participant/context item.",
                    )
                )
                continue
            parents[(target, "entity")].append(source)
            if target_type == "OperationalEntity":
                entity_graph.add_edge(source, target)

    for (target, family), sources in parents.items():
        if len(sources) <= 1:
            continue
        label = {
            "goal": "decomposition",
            "action": "decomposition",
            "entity": "structural",
        }[family]
        issues.append(
            _issue(
                model,
                target,
                f"This item belongs to more than one {label} parent.",
            )
        )

    for graph, message in (
        (goal_graph, "Goal decomposition contains a cycle."),
        (action_graph, "Action decomposition contains a cycle."),
        (entity_graph, "Participant/context composition contains a cycle."),
    ):
        if graph.number_of_edges() and not nx.is_directed_acyclic_graph(graph):
            for component in nx.strongly_connected_components(graph):
                if len(component) > 1 or any(graph.has_edge(node, node) for node in component):
                    focus = sorted(component, key=str)[0]
                    issues.append(_issue(model, focus, message))

    return _dedupe_issues(issues)


def project_rdf_with_decomposition(knowledge, model) -> Graph:
    """Export all persisted composition/decomposition relations into project RDF."""
    project = knowledge.project_rdf(model)

    for source, target, data in model.graph.edges(data=True):
        if data.get("type") != "DECOMPOSES":
            continue
        source_type = _node_type(model, source)
        target_type = _node_type(model, target)
        if source_type != target_type:
            continue
        source_uri = knowledge._project_uri(source)
        target_uri = knowledge._project_uri(target)
        if source_type == "OperationalCapability":
            project.add((source_uri, CAPABILITY_DECOMPOSITION, target_uri))
        elif source_type == "OperationalActivity":
            project.add((source_uri, OA.containsActivity, target_uri))

    return project


def rdf_parity_issues(knowledge, model, project: Graph) -> list[ValidationIssue]:
    """Verify that every supported NetworkX hierarchy edge has an RDF equivalent."""
    issues: list[ValidationIssue] = []
    for source, target, data in model.graph.edges(data=True):
        relation = data.get("type")
        source_type = _node_type(model, source)
        target_type = _node_type(model, target)
        source_uri = knowledge._project_uri(source)
        target_uri = knowledge._project_uri(target)

        expected = None
        if relation == "DECOMPOSES" and source_type == target_type == "OperationalCapability":
            expected = CAPABILITY_DECOMPOSITION
        elif relation == "DECOMPOSES" and source_type == target_type == "OperationalActivity":
            expected = OA.containsActivity
        elif relation == "CONTAINS" and source_type == "OperationalEntity" and target_type in {
            "OperationalEntity",
            "OperationalActor",
        }:
            expected = OA.containsEntity

        if expected is not None and (source_uri, expected, target_uri) not in project:
            issues.append(
                _issue(
                    model,
                    source,
                    "The internal graph and RDF representation disagree about this hierarchy relation.",
                )
            )
    return issues


def _combined_shapes(knowledge) -> Graph:
    shapes = Graph()
    for triple in knowledge.shapes:
        shapes.add(triple)
    supplemental = Graph().parse(data=_SUPPLEMENTAL_SHAPES, format="turtle")
    for triple in supplemental:
        shapes.add(triple)
    return shapes


def _dedupe_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    unique: dict[tuple[str, str, str], ValidationIssue] = {}
    for issue in issues:
        key = (issue.severity, issue.focus_id, issue.message)
        unique.setdefault(key, issue)
    order = {"VIOLATION": 0, "WARNING": 1, "INFO": 2}
    return sorted(
        unique.values(),
        key=lambda issue: (
            order.get(issue.severity, 3),
            issue.focus_name.casefold(),
            issue.message,
        ),
    )


def compare_model_consistently(knowledge, model) -> ModelComparison:
    """Run SHACL plus Feature 5 graph/RDF consistency checks."""
    started = time.perf_counter()
    project = project_rdf_with_decomposition(knowledge, model)
    conforms, report_graph, _ = shacl_validate(
        data_graph=project,
        shacl_graph=_combined_shapes(knowledge),
        ont_graph=knowledge.ontology,
        inference="rdfs",
        advanced=True,
        allow_warnings=True,
        allow_infos=True,
    )

    issues: list[ValidationIssue] = []
    for result in report_graph.subjects(RDF.type, SH.ValidationResult):
        focus = report_graph.value(result, SH.focusNode)
        severity_uri = report_graph.value(result, SH.resultSeverity)
        raw_message = str(report_graph.value(result, SH.resultMessage) or "Model issue")
        message = knowledge._MESSAGE_TRANSLATIONS.get(raw_message, raw_message)
        shape = report_graph.value(result, SH.sourceShape)
        severity = knowledge._local_name(severity_uri or SH.Info).upper()
        focus_id = str(project.value(focus, OA.identifier) or knowledge._local_name(focus or ""))
        focus_name = str(project.value(focus, OA.name) or focus_id)
        issues.append(
            ValidationIssue(
                severity=severity,
                focus_id=focus_id,
                focus_name=focus_name,
                message=message,
                source_shape=knowledge._local_name(shape or ""),
            )
        )

    issues.extend(structural_issues(model))
    issues.extend(rdf_parity_issues(knowledge, model, project))
    issues = _dedupe_issues(issues)
    has_violation = any(issue.severity == "VIOLATION" for issue in issues)
    elapsed = (time.perf_counter() - started) * 1000
    return ModelComparison(
        bool(conforms) and not has_violation,
        tuple(issues),
        len(project),
        elapsed,
    )


def format_model_comparison(comparison: ModelComparison, max_issues: int | None = None) -> str:
    lines = [
        f"Mandatory model rules: {'PASS' if comparison.conforms else 'FAIL'}",
        (
            f"Issues: {comparison.count('VIOLATION')} violation(s), "
            f"{comparison.count('WARNING')} warning(s), "
            f"{comparison.count('INFO')} information item(s)"
        ),
        f"Project RDF: {comparison.project_triples} triples",
    ]
    selected = comparison.issues if max_issues is None else comparison.issues[:max_issues]
    if selected:
        lines.append("")
        for issue in selected:
            lines.append(
                f"- [{issue.severity}] {issue.focus_name} ({issue.focus_id}): {issue.message}"
            )
    if max_issues is not None and len(comparison.issues) > max_issues:
        lines.append(
            f"- ... {len(comparison.issues) - max_issues} more issue(s); use /compare to see all."
        )
    lines.extend(["", f"Elapsed comparison time: {comparison.elapsed_ms:.1f} ms"])
    return "\n".join(lines)
