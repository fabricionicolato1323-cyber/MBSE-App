from __future__ import annotations

import copy

from graph_model import OAGraph
from knowledge_graph import ArcadiaKnowledgeBase
from ontology import ALLOWED_RELATIONS


_ACTOR_CONTAINS_ACTOR = (
    "OperationalActor",
    "CONTAINS",
    "OperationalActor",
)
_BASE_ADD_RELATION = OAGraph.add_relation
_BASE_DECOMPOSITION_CHILDREN = OAGraph.decomposition_children
_BASE_DECOMPOSITION_RELATIONS = OAGraph.decomposition_relations
_BASE_DECOMPOSITION_ISSUES = OAGraph.decomposition_issues
_BASE_PROJECT_RDF = ArcadiaKnowledgeBase.project_rdf
_INSTALLED = False


def _actor_aware_add_relation(
    self: OAGraph,
    source_id: str,
    relation: str,
    target_id: str,
    **attributes,
) -> tuple[bool, str]:
    if (
        relation == "CONTAINS"
        and source_id in self.graph
        and target_id in self.graph
        and self.graph.nodes[source_id].get("type") == "OperationalActor"
        and self.graph.nodes[target_id].get("type") == "OperationalActor"
    ):
        # Nested actors are an application-level grouping requested for the
        # interactive model/diagram. Canonical Arcadia comparison still sees
        # actors as non-decomposable, so the edge is explicitly marked.
        attributes.setdefault("application_only", True)
    return _BASE_ADD_RELATION(
        self, source_id, relation, target_id, **attributes
    )


def _project_rdf_without_application_actor_groups(
    self: ArcadiaKnowledgeBase,
    model,
):
    """Keep application-only actor grouping out of canonical Arcadia checks."""
    if not any(
        data.get("application_only")
        for _, _, data in model.graph.edges(data=True)
    ):
        return _BASE_PROJECT_RDF(self, model)

    project_model = copy.copy(model)
    project_model.graph = model.graph.copy()
    for source, target, key, data in list(
        project_model.graph.edges(keys=True, data=True)
    ):
        if data.get("application_only"):
            project_model.graph.remove_edge(source, target, key=key)
    return _BASE_PROJECT_RDF(self, project_model)


def _actor_aware_decomposition_children(self: OAGraph, node_id: str) -> list[str]:
    if node_id not in self.graph:
        return []
    if self.graph.nodes[node_id].get("type") != "OperationalActor":
        return _BASE_DECOMPOSITION_CHILDREN(self, node_id)
    return [
        target
        for _, target, data in self.graph.out_edges(node_id, data=True)
        if data.get("type") == "CONTAINS"
        and self.graph.nodes[target].get("type") == "OperationalActor"
    ]


def _actor_aware_decomposition_relations(
    self: OAGraph,
) -> list[tuple[str, str, str]]:
    result = list(_BASE_DECOMPOSITION_RELATIONS(self))
    existing = set(result)
    for source, target, data in self.graph.edges(data=True):
        if data.get("type") != "CONTAINS":
            continue
        if self.graph.nodes[source].get("type") != "OperationalActor":
            continue
        if self.graph.nodes[target].get("type") != "OperationalActor":
            continue
        item = (source, target, "CONTAINS")
        if item not in existing:
            result.append(item)
            existing.add(item)
    return result


def _actor_aware_decomposition_issues(self: OAGraph) -> list[str]:
    actor_messages = {
        f"'{self.name(node_id)}' cannot contain smaller participants."
        for node_id, data in self.graph.nodes(data=True)
        if data.get("type") == "OperationalActor"
    }
    issues = [
        issue
        for issue in _BASE_DECOMPOSITION_ISSUES(self)
        if issue not in actor_messages
    ]
    for source, target, data in self.graph.edges(data=True):
        if data.get("type") != "CONTAINS":
            continue
        source_type = self.graph.nodes[source].get("type")
        target_type = self.graph.nodes[target].get("type")
        if source_type == "OperationalActor" and target_type != "OperationalActor":
            issues.append(
                f"Operational Actor '{self.name(source)}' cannot contain "
                f"Operational Entity '{self.name(target)}'."
            )
    return issues


def install_operational_actor_composition_support() -> None:
    """Allow Actor -> Actor composition while keeping Actor -> Entity forbidden.

    The graph class is patched in place so the web worker's AutosaveOAGraph,
    which is defined before app.py is imported, receives the same rules without
    replacing its autosave factory.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    ALLOWED_RELATIONS.add(_ACTOR_CONTAINS_ACTOR)
    OAGraph.add_relation = _actor_aware_add_relation
    OAGraph.decomposition_children = _actor_aware_decomposition_children
    OAGraph.decomposition_relations = _actor_aware_decomposition_relations
    OAGraph.decomposition_issues = _actor_aware_decomposition_issues
    ArcadiaKnowledgeBase.project_rdf = _project_rdf_without_application_actor_groups
    _INSTALLED = True


class OperationalActorCompositionFlowMixin:
    """Expose valid nested Operational Actor composition in the guided flow."""

    def _decomposition_targets(self) -> list[tuple[str, str]]:
        targets = list(super()._decomposition_targets())
        existing = {node_id for node_id, _ in targets}
        for node_id in self.model.nodes_of_type("OperationalActor"):
            if node_id not in existing:
                targets.append(
                    (node_id, f"Person / role: {self.model.name(node_id)}")
                )
        return targets

    def _available_structural_children(self, parent_id: str) -> list[str]:
        available = list(super()._available_structural_children(parent_id))
        if self.model.graph.nodes[parent_id].get("type") != "OperationalActor":
            return available
        return [
            node_id
            for node_id in available
            if self.model.graph.nodes[node_id].get("type") == "OperationalActor"
        ]

    def _create_participant_child(self, parent_id: str) -> str | None:
        if self.model.graph.nodes[parent_id].get("type") != "OperationalActor":
            return super()._create_participant_child(parent_id)

        while True:
            node_type, participant_name, classification = self.ask_participant()
            if node_type != "OperationalActor":
                self.add_notice(
                    "Operational Actors may contain only other Operational Actors. "
                    "Operational Entities cannot be placed inside an Operational Actor."
                )
                if not self.ask_yes_no(
                    "Would you like to define an Operational Actor instead?",
                    "Actor composition can continue only with another person / role.",
                ):
                    return None
                continue

            existing = self.model.find_participant_duplicate(participant_name)
            if existing is not None:
                if existing == parent_id:
                    self.add_notice("An item cannot contain itself.")
                    return None
                if self.model.graph.nodes[existing].get("type") != "OperationalActor":
                    self.add_notice(
                        "An Operational Entity with that name already exists and cannot "
                        "be placed inside an Operational Actor."
                    )
                    return None
                if not self.ask_yes_no(
                    f"'{self.model.name(existing)}' already exists. Use it as the smaller actor?",
                    "Reusing an existing person / role avoids duplicates.",
                ):
                    self.add_notice("Nothing was added for that smaller actor.")
                    return None
                return existing

            expects_activity = self.activity_expectation_for(
                node_type,
                participant_name,
            )
            child_id = self.add_node(
                node_type,
                participant_name,
                expects_activity=expects_activity,
                **classification,
            )
            if not child_id:
                return None
            if self.model.expects_activity(child_id):
                self.capture_actions_for_participant(child_id)
            return child_id
