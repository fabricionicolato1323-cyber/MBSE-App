from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from typing import Any

from arcadia_oa_library import DEFAULT_ARCADIA_OA_LIBRARY
from exchange_transport import ExchangeTransportError, relationship_identity, resolve_exchange_transport
from sam_connection import SamSettings
from sysml_v2 import generate_sysml_v2


class SamLevel1SyncError(RuntimeError):
    """Raised when a Level 1 snapshot cannot be safely synchronized to SAM."""


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _slug(value: Any, fallback: str = "Operational_Analysis") -> str:
    text = unicodedata.normalize("NFKD", _clean(value)).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "_".join(words)[:64] or fallback


def _model_name(model: dict[str, Any]) -> str:
    graph = model.get("graph", {}) if isinstance(model.get("graph"), dict) else {}
    return _clean(graph.get("model_name") or graph.get("model") or "Operational Analysis")


def _stable_snapshot(
    model: dict[str, Any],
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    def stable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            rows,
            key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str),
        )

    return {
        "model_name": _model_name(model),
        "nodes": stable(_rows(model.get("nodes"))),
        "edges": stable(_rows(model.get("edges"))),
        "scenarios": stable([item for item in scenarios if item.get("valid") is not False]),
    }


def level1_snapshot_digest(
    payload: Any,
    scenarios: list[dict[str, Any]] | None = None,
) -> str:
    model = payload if isinstance(payload, dict) else {}
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    canonical = json.dumps(
        _stable_snapshot(model, scenario_rows),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _allowed_relation(
    edge: dict[str, Any],
    mapping: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
) -> bool:
    source = node_by_id.get(str(edge.get("source") or ""), {})
    target = node_by_id.get(str(edge.get("target") or ""), {})
    variants = mapping.get("variants")
    if isinstance(variants, list) and variants:
        return any(
            isinstance(variant, dict)
            and source.get("type") == variant.get("source_node_type")
            and target.get("type") == variant.get("target_node_type")
            for variant in variants
        )
    source_types = set(mapping.get("source_node_types") or [])
    target_types = set(mapping.get("target_node_types") or [])
    return (
        (not source_types or source.get("type") in source_types)
        and (not target_types or target.get("type") in target_types)
    )


def build_level1_sync_plan(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Build a no-write Level 1B plan for the current confirmed model snapshot."""
    model = payload if isinstance(payload, dict) else {}
    nodes = _rows(model.get("nodes"))
    edges = _rows(model.get("edges"))
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    valid_scenarios = [item for item in scenario_rows if item.get("valid") is not False]
    node_by_id = {str(node.get("id")): node for node in nodes if node.get("id") is not None}

    contract = DEFAULT_ARCADIA_OA_LIBRARY.contract
    node_mappings = contract.get("node_types", {})
    relation_mappings = contract.get("relationships", {})
    unsupported_nodes = [
        {
            "id": str(node.get("id") or ""),
            "type": str(node.get("type") or "UNKNOWN"),
            "name": _clean(node.get("name") or node.get("id")),
        }
        for node in nodes
        if str(node.get("type") or "") not in node_mappings
    ]
    unsupported_relations: list[dict[str, str]] = []
    strategy_counts: dict[str, int] = defaultdict(int)
    for edge in edges:
        relation = str(edge.get("type") or "")
        mapping = relation_mappings.get(relation)
        if (
            not isinstance(mapping, dict)
            or mapping.get("strategy") == "unmapped"
            or not _allowed_relation(edge, mapping, node_by_id)
            or str(edge.get("source") or "") not in node_by_id
            or str(edge.get("target") or "") not in node_by_id
        ):
            unsupported_relations.append(
                {
                    "type": relation or "UNKNOWN",
                    "source": str(edge.get("source") or ""),
                    "target": str(edge.get("target") or ""),
                    "name": _clean(edge.get("name")),
                }
            )
            continue
        strategy_counts[str(mapping.get("strategy"))] += 1

    digest = level1_snapshot_digest(model, valid_scenarios)
    package_name = f"MBSE_Level1_{_slug(_model_name(model))}_{digest[:8]}"
    blocked = bool(unsupported_nodes or unsupported_relations or not nodes)
    return {
        "level": 1,
        "phase": "B",
        "mode": "transactional_create_only_snapshot",
        "status": "blocked" if blocked else "ready",
        "snapshot_digest": digest,
        "package_name": package_name,
        "model_name": _model_name(model),
        "target_project_id": project_id,
        "counts": {
            "elements": len(nodes),
            "relationships": len(edges),
            "scenarios": len(valid_scenarios),
            "relationship_strategies": dict(sorted(strategy_counts.items())),
        },
        "unsupported_nodes": unsupported_nodes,
        "unsupported_relations": unsupported_relations,
        "sam_write_performed": False,
    }


def _documentation(factory: Any, element: Any, body: str) -> Any:
    return factory.create_documentation(
        owner=element,
        documented_element=element,
        body=body,
        locale="en",
    )


def _source_document(node_or_edge: dict[str, Any], kind: str) -> str:
    return (
        f"MBSE-App Level 1B source {kind}.\n"
        + json.dumps(node_or_edge, ensure_ascii=False, sort_keys=True, default=str)
    )


def _create_library_definitions(factory: Any, owner: Any) -> dict[str, Any]:
    definitions_package = factory.create_package(name="ArcadiaOA", owner=owner)
    operational_entity = factory.create_part_definition(
        name="OperationalEntity", owner=definitions_package
    )
    operational_actor = factory.create_part_definition(
        name="OperationalActor", owner=definitions_package
    )
    factory.create_subclassification(
        owner=operational_actor,
        subclassifier=operational_actor,
        superclassifier=operational_entity,
        source=[operational_actor],
        target=[operational_entity],
    )
    return {
        "definitions_package": definitions_package,
        "OperationalEntity": operational_entity,
        "OperationalActor": operational_actor,
        "OperationalActivity": factory.create_action_definition(
            name="OperationalActivity", owner=definitions_package
        ),
        "OperationalInformation": factory.create_item_definition(
            name="OperationalInformation", owner=definitions_package
        ),
        "OperationalExchange": factory.create_flow_connection_definition(
            name="OperationalExchange", owner=definitions_package
        ),
        "CommunicationMean": factory.create_connection_definition(
            name="CommunicationMean", owner=definitions_package
        ),
        "OperationalScenario": factory.create_action_definition(
            name="OperationalScenario", owner=definitions_package
        ),
        "OperationalCapability": factory.create_requirement_definition(
            name="OperationalCapability", owner=definitions_package
        ),
    }


def _nested_parent_map(
    edges: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    relationships = DEFAULT_ARCADIA_OA_LIBRARY.contract.get("relationships", {})
    parents: dict[str, str] = {}
    for edge in edges:
        mapping = relationships.get(str(edge.get("type") or ""))
        if not isinstance(mapping, dict) or mapping.get("strategy") != "nested_usage":
            continue
        if not _allowed_relation(edge, mapping, node_by_id):
            continue
        parent = str(edge.get(str(mapping.get("parent_endpoint") or "source")) or "")
        child = str(edge.get(str(mapping.get("child_endpoint") or "target")) or "")
        if child in parents and parents[child] != parent:
            raise SamLevel1SyncError(
                f"Element {child!r} has more than one Level 1 nesting parent."
            )
        parents[child] = parent

    for child in parents:
        seen: set[str] = set()
        current = child
        while current in parents:
            if current in seen:
                raise SamLevel1SyncError("A containment/decomposition cycle blocks SAM transfer.")
            seen.add(current)
            current = parents[current]
    return parents


def _create_characteristics(factory: Any, owner: Any, node: dict[str, Any]) -> int:
    created = 0
    for item in _rows(node.get("characteristics")):
        name = _clean(item.get("name")) or "Characteristic"
        kind = _clean(item.get("value_type")).casefold()
        if kind == "range":
            for suffix, key in (("lower", "lower_bound"), ("upper", "upper_bound")):
                attribute = factory.create_attribute_usage(
                    name=f"{name} {suffix}", owner=owner
                )
                _documentation(
                    factory,
                    attribute,
                    json.dumps(
                        {
                            "source_characteristic": name,
                            "bound": suffix,
                            "value": item.get(key),
                            "unit": item.get("unit"),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                )
                created += 1
        else:
            attribute = factory.create_attribute_usage(name=name, owner=owner)
            _documentation(
                factory,
                attribute,
                json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
            )
            created += 1
    return created


def _create_source_nodes(
    factory: Any,
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    definitions: dict[str, Any],
    model_package: Any,
) -> tuple[dict[str, Any], Any, Any, int]:
    node_by_id = {str(node.get("id")): node for node in nodes}
    parents = _nested_parent_map(edges, node_by_id)
    structure = factory.create_part_usage(name="oa_operationalContext", owner=model_package)
    behavior = factory.create_action_usage(name="oa_operationalBehavior", owner=model_package)
    created: dict[str, Any] = {}
    characteristic_count = 0

    def create_one(node_id: str) -> Any:
        nonlocal characteristic_count
        if node_id in created:
            return created[node_id]
        node = node_by_id[node_id]
        parent_id = parents.get(node_id)
        node_type = str(node.get("type") or "")
        if parent_id:
            owner = create_one(parent_id)
        elif node_type in {"OperationalEntity", "OperationalActor"}:
            owner = structure
        elif node_type == "OperationalActivity":
            owner = behavior
        else:
            owner = model_package

        name = _clean(node.get("name") or node_id)
        if node_type == "OperationalEntity":
            element = factory.create_part_usage(
                name=name,
                owner=owner,
                part_definition=[definitions["OperationalEntity"]],
            )
        elif node_type == "OperationalActor":
            element = factory.create_part_usage(
                name=name,
                owner=owner,
                part_definition=[definitions["OperationalActor"]],
                is_actor=True,
            )
        elif node_type == "OperationalActivity":
            element = factory.create_action_usage(
                name=name,
                owner=owner,
                action_definition=[definitions["OperationalActivity"]],
            )
        elif node_type == "OperationalCapability":
            element = factory.create_requirement_usage(
                name=name,
                owner=owner,
                requirement_definition=definitions["OperationalCapability"],
                req_id=node_id,
            )
        else:
            raise SamLevel1SyncError(f"Unsupported node type reached writer: {node_type}")
        created[node_id] = element
        _documentation(factory, element, _source_document(node, "element"))
        characteristic_count += _create_characteristics(factory, element, node)
        return element

    for node_id in sorted(node_by_id):
        create_one(node_id)
    return created, structure, behavior, characteristic_count


def _relation_name(edge: dict[str, Any]) -> str:
    return _clean(edge.get("name")) or str(edge.get("type") or "Relationship")


def _create_relationships(
    factory: Any,
    *,
    edges: list[dict[str, Any]],
    elements: dict[str, Any],
    definitions: dict[str, Any],
    model_package: Any,
    structure: Any,
    behavior: Any,
) -> int:
    mappings = DEFAULT_ARCADIA_OA_LIBRARY.contract.get("relationships", {})
    created_count = 0
    communication_usages: dict[str, Any] = {}

    # Create every non-flow relationship first so a Communication Mean usage can
    # own the FlowConnectionUsage instances that it carries.
    for edge in edges:
        relation = str(edge.get("type") or "")
        mapping = mappings[relation]
        strategy = str(mapping.get("strategy") or "")
        if strategy in {"nested_usage", "flow"}:
            continue

        source = elements[str(edge.get("source") or "")]
        target = elements[str(edge.get("target") or "")]
        name = _relation_name(edge)
        if strategy == "perform":
            relationship = factory.create_perform_action_usage(
                name=name,
                owner=source,
                performed_action=target,
            )
        elif strategy == "connection":
            relationship = factory.create_connection_usage(
                name=name,
                owner=structure,
                connection_definition=[definitions["CommunicationMean"]],
                source=[source],
                target=[target],
                source_feature=source,
                target_feature=[target],
                related_feature=[source, target],
                is_directed=False,
            )
            communication_usages[relationship_identity(edge)] = relationship
        elif strategy == "allocation":
            from_id = str(edge.get(str(mapping.get("from_endpoint") or "source")) or "")
            to_id = str(edge.get(str(mapping.get("to_endpoint") or "target")) or "")
            from_element = elements[from_id]
            to_element = elements[to_id]
            relationship = factory.create_allocation_usage(
                name=name,
                owner=model_package,
                source=[from_element],
                target=[to_element],
                source_feature=from_element,
                target_feature=[to_element],
                related_feature=[from_element, to_element],
                is_directed=True,
            )
        elif strategy == "reference":
            owner_id = str(edge.get(str(mapping.get("owner_endpoint") or "source")) or "")
            referenced_id = str(
                edge.get(str(mapping.get("referenced_endpoint") or "target")) or ""
            )
            owner_element = elements[owner_id]
            referenced = elements[referenced_id]
            relationship = factory.create_reference_usage(
                name=name,
                owner=owner_element,
                reference_type=[definitions["OperationalEntity"]],
                type_=[definitions["OperationalEntity"]],
                referenced_feature=[referenced],
            )
        else:
            raise SamLevel1SyncError(
                f"Unsupported relationship strategy reached writer: {strategy}"
            )
        _documentation(factory, relationship, _source_document(edge, "relationship"))
        created_count += 1

    for edge in edges:
        relation = str(edge.get("type") or "")
        mapping = mappings[relation]
        if str(mapping.get("strategy") or "") != "flow":
            continue
        source = elements[str(edge.get("source") or "")]
        target = elements[str(edge.get("target") or "")]
        try:
            transport = resolve_exchange_transport(edges, edge)
        except ExchangeTransportError as exc:
            raise SamLevel1SyncError(str(exc)) from exc
        owner = behavior
        if transport is not None:
            owner = communication_usages.get(relationship_identity(transport))
            if owner is None:
                raise SamLevel1SyncError(
                    f"Communication Mean {_relation_name(transport)!r} was not created before "
                    f"Operational Exchange {_relation_name(edge)!r}."
                )
        relationship = factory.create_flow_connection_usage(
            name=_relation_name(edge),
            owner=owner,
            flow_connection_definition=[definitions["OperationalExchange"]],
            source=[source],
            target=[target],
            source_feature=source,
            target_feature=[target],
            related_feature=[source, target],
            is_directed=True,
        )
        _documentation(factory, relationship, _source_document(edge, "relationship"))
        created_count += 1
    return created_count


def _create_scenarios(
    factory: Any,
    *,
    scenarios: list[dict[str, Any]],
    source_nodes: dict[str, dict[str, Any]],
    definitions: dict[str, Any],
    model_package: Any,
) -> tuple[int, int]:
    scenario_count = 0
    step_count = 0
    for scenario in scenarios:
        if scenario.get("valid") is False:
            continue
        steps = [item for item in _rows(scenario.get("steps")) if item.get("kind") in {"activity", "interaction"}]
        activity_steps = [item for item in steps if item.get("kind") == "activity"]
        if not activity_steps:
            continue
        scenario_usage = factory.create_action_usage(
            name=_clean(scenario.get("name") or scenario.get("id") or "Operational Scenario"),
            owner=model_package,
            action_definition=[definitions["OperationalScenario"]],
        )
        _documentation(factory, scenario_usage, _source_document(scenario, "scenario"))
        scenario_count += 1
        usages: list[Any] = []
        for index, step in enumerate(activity_steps, start=1):
            source_id = str(step.get("activity_id") or "")
            source_node = source_nodes.get(source_id, {})
            usage = factory.create_action_usage(
                name=f"{index}. {_clean(source_node.get('name') or source_id or 'Activity')}",
                owner=scenario_usage,
                action_definition=[definitions["OperationalActivity"]],
            )
            _documentation(
                factory,
                usage,
                f"Scenario step references MBSE-App activity id: {source_id}",
            )
            usages.append(usage)
            step_count += 1
        for before, after in zip(usages, usages[1:]):
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


def _load_pysam_classes():
    try:
        from ansys.sam.sysml2 import AnsysSysML2APIConnector, SysML2ProjectManager
        from ansys.sam.sysml2.tools import Factory
    except ImportError as exc:  # pragma: no cover - exercised only without optional dependency.
        raise SamLevel1SyncError(
            "PySAM SysML2 is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc
    return AnsysSysML2APIConnector, SysML2ProjectManager, Factory


def sync_level1_to_sam(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None,
    settings: SamSettings,
    expected_digest: str | None = None,
    connector_class: type[Any] | None = None,
    project_manager_class: type[Any] | None = None,
    factory_class: type[Any] | None = None,
) -> dict[str, Any]:
    """Create one immutable Level 1 snapshot package in the configured SAM project."""
    model = payload if isinstance(payload, dict) else {}
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    plan = build_level1_sync_plan(
        model,
        scenarios=scenario_rows,
        project_id=settings.project_id,
    )
    if plan["status"] != "ready":
        raise SamLevel1SyncError(
            "Level 1 transfer is blocked because the snapshot contains unsupported or missing semantic content."
        )
    if expected_digest and expected_digest != plan["snapshot_digest"]:
        raise SamLevel1SyncError(
            "The model changed after the transfer plan was prepared. Review the new plan before sending."
        )

    if connector_class is None or project_manager_class is None or factory_class is None:
        default_connector, default_manager, default_factory = _load_pysam_classes()
        connector_class = connector_class or default_connector
        project_manager_class = project_manager_class or default_manager
        factory_class = factory_class or default_factory

    connector = connector_class(
        server_url=settings.server_url,
        organization_id=settings.organization_id,
        token=settings.access_token,
        use_ssl=settings.use_ssl,
    )
    manager = project_manager_class(connector=connector)
    project = manager.get_scripting_project(settings.project_id)
    if project is None:
        raise SamLevel1SyncError("The configured SAM project could not be loaded.")

    existing = project.find_elements_by_name(plan["package_name"])
    if existing:
        return {
            **plan,
            "status": "already_synced",
            "sam_write_performed": False,
            "sam_package_id": getattr(existing[0], "id", None),
        }

    root = project.get_root_package()
    factory = factory_class(project, connector)
    project.start_transactional_mode()
    try:
        model_package = factory.create_package(name=plan["package_name"], owner=root)
        _documentation(
            factory,
            model_package,
            "MBSE-App Level 1B immutable snapshot.\n"
            f"Model: {plan['model_name']}\n"
            f"Snapshot SHA-256: {plan['snapshot_digest']}\n"
            f"Source elements: {plan['counts']['elements']}\n"
            f"Source relationships: {plan['counts']['relationships']}\n"
            f"Operational scenarios: {plan['counts']['scenarios']}",
        )
        definitions = _create_library_definitions(factory, model_package)
        nodes = _rows(model.get("nodes"))
        edges = _rows(model.get("edges"))
        source_node_by_id = {str(node.get("id")): node for node in nodes}
        elements, structure, behavior, characteristic_count = _create_source_nodes(
            factory,
            nodes=nodes,
            edges=edges,
            definitions=definitions,
            model_package=model_package,
        )
        relationship_count = _create_relationships(
            factory,
            edges=edges,
            elements=elements,
            definitions=definitions,
            model_package=model_package,
            structure=structure,
            behavior=behavior,
        )
        scenario_count, scenario_step_count = _create_scenarios(
            factory,
            scenarios=scenario_rows,
            source_nodes=source_node_by_id,
            definitions=definitions,
            model_package=model_package,
        )
        sysml_text = generate_sysml_v2(model, scenarios=scenario_rows, drafts=[])
        factory.create_textual_representation(
            owner=model_package,
            represented_element=model_package,
            language="SysML v2",
            body=sysml_text,
        )
        project.stop_transactional_mode()
    except Exception as exc:
        # Do not call stop_transactional_mode(): until that call PySAM keeps the
        # transaction local and no partial snapshot is committed to the server.
        raise SamLevel1SyncError(f"SAM Level 1 transaction failed: {exc}") from exc

    return {
        **plan,
        "status": "synced",
        "sam_write_performed": True,
        "sam_package_id": getattr(model_package, "id", None),
        "created": {
            "source_elements": len(elements),
            "native_relationships": relationship_count,
            "characteristic_attributes": characteristic_count,
            "scenarios": scenario_count,
            "scenario_steps": scenario_step_count,
            "textual_level1_representation": 1,
        },
    }
