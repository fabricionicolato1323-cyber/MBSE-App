from __future__ import annotations

import json
import re
from typing import Any

from sam_full_projection import SAMProjectionAnalysis
from sam_reference_profile import SAMReferenceProfile


class SAMFullProjectionWriteError(RuntimeError):
    """Raised when a validated SAM projection cannot be materialized through PySAM."""


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _documentation(factory: Any, element: Any, body: str) -> Any:
    return factory.create_documentation(
        owner=element,
        documented_element=element,
        body=body,
        locale="en",
    )


def _source_document(value: dict[str, Any], kind: str) -> str:
    return (
        f"MBSE-App SAM full projection source {kind}.\n"
        + json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    )


def _definition_name(profile: SAMReferenceProfile, concept: str) -> str:
    return str(profile.definition(concept).get("sysml_name") or concept)


def create_sam_reference_definitions(
    factory: Any,
    owner: Any,
    profile: SAMReferenceProfile,
) -> dict[str, Any]:
    """Materialize the reference library definitions under one namespace package."""
    namespace = factory.create_package(
        name=profile.exported_library_package,
        owner=owner,
    )
    operational_entity = factory.create_part_definition(
        name=_definition_name(profile, "OperationalEntity"), owner=namespace
    )
    operational_actor = factory.create_part_definition(
        name=_definition_name(profile, "OperationalActor"), owner=namespace
    )
    factory.create_subclassification(
        owner=operational_actor,
        subclassifier=operational_actor,
        superclassifier=operational_entity,
        source=[operational_actor],
        target=[operational_entity],
    )
    definitions = {
        "namespace": namespace,
        "OperationalEntity": operational_entity,
        "OperationalActor": operational_actor,
        "OperationalActivity": factory.create_action_definition(
            name=_definition_name(profile, "OperationalActivity"), owner=namespace
        ),
        "OperationalExchange": factory.create_flow_connection_definition(
            name=_definition_name(profile, "OperationalExchange"), owner=namespace
        ),
        "CommunicationMean": factory.create_interface_definition(
            name=_definition_name(profile, "CommunicationMean"), owner=namespace
        ),
        "OperationalConstraint": factory.create_constraint_definition(
            name=_definition_name(profile, "OperationalConstraint"), owner=namespace
        ),
        "OperationalScenario": factory.create_action_definition(
            name=_definition_name(profile, "OperationalScenario"), owner=namespace
        ),
        "OperationalCapability": factory.create_requirement_definition(
            name=_definition_name(profile, "OperationalCapability"), owner=namespace
        ),
    }
    _documentation(
        factory,
        namespace,
        "Definitions generated from sysml/SAM_OA.reference.json. Communication Mean "
        "is retained as a library definition but is not projected as model content in this phase.",
    )
    return definitions


def create_projection_packages(
    factory: Any,
    model_package: Any,
    profile: SAMReferenceProfile,
) -> dict[str, Any]:
    structure = profile.contract["model_structure"]
    containers = structure["containers"]
    oa = factory.create_package(
        name=str(structure.get("oa_package") or "Arcadia_OA"), owner=model_package
    )
    return {
        "oa": oa,
        "structure": factory.create_package(name=containers["structure"], owner=oa),
        "requirements": factory.create_package(name=containers["requirements"], owner=oa),
        "scenarios": factory.create_package(name=containers["scenarios"], owner=oa),
    }


def _create_characteristics(factory: Any, owner: Any, node: dict[str, Any]) -> int:
    created = 0
    for item in _rows(node.get("characteristics")):
        name = _clean(item.get("name")) or "Characteristic"
        if _clean(item.get("value_type")).casefold() == "range":
            values = (("lower", "lower_bound"), ("upper", "upper_bound"))
        else:
            values = (("value", "value"),)
        for suffix, key in values:
            attribute_name = name if suffix == "value" else f"{name} {suffix}"
            attribute = factory.create_attribute_usage(name=attribute_name, owner=owner)
            _documentation(
                factory,
                attribute,
                json.dumps(
                    {
                        "source_characteristic": name,
                        "kind": suffix,
                        "value": item.get(key),
                        "unit": item.get("unit"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            )
            created += 1
    return created


def create_projection_nodes(
    factory: Any,
    *,
    analysis: SAMProjectionAnalysis,
    definitions: dict[str, Any],
    packages: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Create participants, nested activities, and nested capabilities."""
    node_by_id = analysis.node_by_id
    created: dict[str, Any] = {}
    characteristic_count = 0

    def participant(node_id: str) -> Any:
        nonlocal characteristic_count
        if node_id in created:
            return created[node_id]
        node = node_by_id[node_id]
        parent = analysis.participant_parent.get(node_id)
        owner = participant(parent) if parent else packages["structure"]
        node_type = str(node.get("type") or "")
        kwargs = {
            "name": _clean(node.get("name") or node_id),
            "owner": owner,
            "part_definition": [definitions[node_type]],
        }
        if node_type == "OperationalActor":
            kwargs["is_actor"] = True
        element = factory.create_part_usage(**kwargs)
        created[node_id] = element
        _documentation(factory, element, _source_document(node, "element"))
        characteristic_count += _create_characteristics(factory, element, node)
        return element

    def activity(node_id: str) -> Any:
        nonlocal characteristic_count
        if node_id in created:
            return created[node_id]
        node = node_by_id[node_id]
        parent = analysis.activity_parent.get(node_id)
        if parent:
            owner = activity(parent)
        else:
            performer = analysis.effective_performer.get(node_id, "")
            if not performer:
                raise SAMFullProjectionWriteError(
                    f"Operational Activity {node_id!r} has no resolved performer."
                )
            owner = participant(performer)
        element = factory.create_action_usage(
            name=_clean(node.get("name") or node_id),
            owner=owner,
            action_definition=[definitions["OperationalActivity"]],
        )
        created[node_id] = element
        _documentation(factory, element, _source_document(node, "element"))
        characteristic_count += _create_characteristics(factory, element, node)
        return element

    def capability(node_id: str) -> Any:
        nonlocal characteristic_count
        if node_id in created:
            return created[node_id]
        node = node_by_id[node_id]
        parent = analysis.capability_parent.get(node_id)
        owner = capability(parent) if parent else packages["requirements"]
        element = factory.create_requirement_usage(
            name=_clean(node.get("name") or node_id),
            owner=owner,
            requirement_definition=definitions["OperationalCapability"],
            req_id=node_id,
        )
        created[node_id] = element
        _documentation(factory, element, _source_document(node, "element"))
        characteristic_count += _create_characteristics(factory, element, node)
        return element

    for node_id, node in sorted(node_by_id.items()):
        node_type = str(node.get("type") or "")
        if node_type in {"OperationalEntity", "OperationalActor"}:
            participant(node_id)
        elif node_type == "OperationalActivity":
            activity(node_id)
        elif node_type == "OperationalCapability":
            capability(node_id)
        else:
            raise SAMFullProjectionWriteError(
                f"Unsupported node type reached SAM full projection writer: {node_type!r}."
            )
    return created, characteristic_count


def create_projection_relationships(
    factory: Any,
    *,
    analysis: SAMProjectionAnalysis,
    elements: dict[str, Any],
    definitions: dict[str, Any],
    packages: dict[str, Any],
) -> int:
    """Create only relations not already encoded by ownership/nesting.

    Communication Mean never reaches this function because the profile classifies
    it as ``ignore``. The reload-safe direct transport represents capability
    support as SatisfyRequirementUsage internally; therefore AllocationUsage is
    called with capability/activity transport orientation while the reviewed
    textual projection retains the SAM-exported ``allocate activity to capability``
    notation.
    """
    count = 0
    for strategy in ("flow", "allocation", "reference"):
        for edge in analysis.classified_edges.get(strategy, []):
            source_id = str(edge.get("source") or "")
            target_id = str(edge.get("target") or "")
            source = elements[source_id]
            target = elements[target_id]
            name = _clean(edge.get("name")) or str(edge.get("type") or "Relationship")
            if strategy == "flow":
                relation = factory.create_flow_connection_usage(
                    name=name,
                    owner=packages["structure"],
                    flow_connection_definition=[definitions["OperationalExchange"]],
                    source=[source],
                    target=[target],
                    source_feature=source,
                    target_feature=[target],
                    related_feature=[source, target],
                    is_directed=True,
                )
            elif strategy == "allocation":
                relation = factory.create_allocation_usage(
                    name=name,
                    owner=packages["requirements"],
                    source=[target],
                    target=[source],
                    source_feature=target,
                    target_feature=[source],
                    related_feature=[target, source],
                    is_directed=True,
                )
            else:
                relation = factory.create_reference_usage(
                    name=name,
                    owner=source,
                    reference_type=[definitions["OperationalEntity"]],
                    type_=[definitions["OperationalEntity"]],
                    referenced_feature=[target],
                )
            _documentation(factory, relation, _source_document(edge, "relationship"))
            count += 1
    return count


def create_projection_scenarios(
    factory: Any,
    *,
    analysis: SAMProjectionAnalysis,
    elements: dict[str, Any],
    definitions: dict[str, Any],
    packages: dict[str, Any],
) -> tuple[int, int]:
    """Create scenarios as references to the already-created operational activities."""
    scenario_count = 0
    step_count = 0
    for scenario in analysis.scenarios:
        if scenario.get("valid") is False:
            continue
        steps = [item for item in _rows(scenario.get("steps")) if item.get("kind") == "activity"]
        if not steps:
            continue
        scenario_usage = factory.create_action_usage(
            name=_clean(scenario.get("name") or scenario.get("id") or "Operational Scenario"),
            owner=packages["scenarios"],
            action_definition=[definitions["OperationalScenario"]],
        )
        _documentation(factory, scenario_usage, _source_document(scenario, "scenario"))
        scenario_count += 1
        performed: list[Any] = []
        used_names: set[str] = set()
        for index, step in enumerate(steps, start=1):
            activity_id = str(step.get("activity_id") or "")
            source = elements[activity_id]
            activity_name = _clean(analysis.node_by_id[activity_id].get("name") or activity_id)
            step_name = f"performaction {activity_name}"
            if step_name.casefold() in used_names:
                step_name = f"{step_name} {index}"
            used_names.add(step_name.casefold())
            usage = factory.create_perform_action_usage(
                name=step_name,
                owner=scenario_usage,
                performed_action=source,
            )
            _documentation(
                factory,
                usage,
                f"Scenario step references MBSE-App activity id: {activity_id}",
            )
            performed.append(usage)
            step_count += 1
        for before, after in zip(performed, performed[1:]):
            factory.create_succession(
                owner=scenario_usage,
                source=[before],
                target=[after],
                source_feature=before,
                target_feature=[after],
                related_feature=[before, after],
                trigger_step=[before],
                effect_step=[after],
            )
    return scenario_count, step_count
