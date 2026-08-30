from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import defaultdict
from typing import Any

from arcadia_oa_library import ArcadiaOALibrary, DEFAULT_ARCADIA_OA_LIBRARY

ARCADIA_OA_LIBRARY_TEXT = DEFAULT_ARCADIA_OA_LIBRARY.sysml_text.rstrip()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _stem(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean(value)).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "_".join(words) or "element"


def _id(value: Any, prefix: str, used: set[str]) -> str:
    base = f"{prefix}_{_stem(value)}"
    result = base
    index = 2
    while result in used:
        result = f"{base}_{index}"
        index += 1
    used.add(result)
    return result


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        parsed = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _num_text(value: int | float) -> str:
    return str(value) if isinstance(value, int) else format(value, ".15g")


def _comments(text: str, indent: str = "") -> list[str]:
    return [f"{indent}// {_clean(text)}"] if _clean(text) else []


def _node_key(node: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(node.get("type") or ""),
        _clean(node.get("name")).casefold(),
        str(node.get("id") or ""),
    )


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(edge.get("type") or ""),
        str(edge.get("source") or ""),
        str(edge.get("target") or ""),
        str(edge.get("key") or ""),
        _clean(edge.get("name")).casefold(),
    )


def _characteristics(
    values: Any,
    indent: str,
    library: ArcadiaOALibrary,
) -> list[str]:
    config = library.contract.get("characteristics", {})
    if config.get("strategy") != "attributes" or not isinstance(values, list):
        return []
    prefix = str(config.get("identifier_prefix") or "oa_attr")
    scalar = config.get("scalar_types", {})
    unit_strategy = str(config.get("unit_strategy") or "comment_only")
    range_strategy = str(config.get("range_strategy") or "")
    used: set[str] = set()
    lines: list[str] = []

    for item in values:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name")) or "Characteristic"
        kind = _clean(item.get("value_type")).casefold()
        unit = _clean(item.get("unit"))

        if kind == "range" and range_strategy == "lower_upper_attributes":
            for suffix, key in (("lower", "lower_bound"), ("upper", "upper_bound")):
                identifier = _id(f"{name} {suffix}", prefix, used)
                value = _number(item.get(key))
                if value is None:
                    lines.append(f"{indent}attribute {identifier};")
                else:
                    type_name = scalar["integer"] if isinstance(value, int) else scalar["real"]
                    lines.append(
                        f"{indent}attribute {identifier} : {type_name} = {_num_text(value)};"
                    )
            if unit and unit_strategy == "comment_only":
                lines += _comments(f"unit for {name}: {unit}", indent)
            continue

        identifier = _id(name, prefix, used)
        if kind == "number":
            value = _number(item.get("value"))
            if value is None:
                lines.append(f"{indent}attribute {identifier};")
            else:
                type_name = scalar["integer"] if isinstance(value, int) else scalar["real"]
                lines.append(
                    f"{indent}attribute {identifier} : {type_name} = {_num_text(value)};"
                )
            if unit and unit_strategy == "comment_only":
                lines += _comments(f"unit: {unit}", indent)
        elif kind == "text":
            value = json.dumps(_clean(item.get("value")), ensure_ascii=False)
            lines.append(f"{indent}attribute {identifier} : {scalar['string']} = {value};")
        else:
            lines.append(f"{indent}attribute {identifier};")
            lines += _comments(
                "Characteristic value kind is not mapped by the library; value omitted.",
                indent,
            )
    return lines


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


def _unmapped_relation_comment(
    edge: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
    indent: str,
) -> list[str]:
    source = str(edge.get("source") or "")
    target = str(edge.get("target") or "")
    source_name = _clean(node_by_id.get(source, {}).get("name") or source)
    target_name = _clean(node_by_id.get(target, {}).get("name") or target)
    relation = _clean(edge.get("type") or "UNKNOWN_RELATION")
    return _comments(
        f"UNMAPPED Arcadia relation {relation}: {source_name} -> {target_name}",
        indent,
    )


def _hierarchy(
    rows: list[tuple[dict[str, Any], dict[str, Any]]],
    identifiers: dict[str, str],
) -> tuple[dict[str, str], dict[str, list[str]], list[dict[str, Any]]]:
    parents: dict[str, str] = {}
    children: dict[str, list[str]] = defaultdict(list)
    rejected: list[dict[str, Any]] = []

    def creates_cycle(parent: str, child: str) -> bool:
        if parent == child:
            return True
        current = parent
        seen: set[str] = set()
        while current in parents and current not in seen:
            if current == child:
                return True
            seen.add(current)
            current = parents[current]
        return current == child

    for edge, mapping in sorted(rows, key=lambda item: _edge_key(item[0])):
        parent_endpoint = str(mapping.get("parent_endpoint") or "source")
        child_endpoint = str(mapping.get("child_endpoint") or "target")
        parent = str(edge.get(parent_endpoint) or "")
        child = str(edge.get(child_endpoint) or "")
        if (
            parent not in identifiers
            or child not in identifiers
            or child in parents
            or creates_cycle(parent, child)
        ):
            rejected.append(edge)
            continue
        parents[child] = parent
        children[parent].append(child)

    for values in children.values():
        values.sort(key=lambda item: identifiers.get(item, item))
    return parents, children, rejected


def _paths_for(
    node_ids: set[str],
    parents: dict[str, str],
    identifiers: dict[str, str],
) -> dict[str, str]:
    paths: dict[str, str] = {}

    def path_for(node_id: str) -> str:
        if node_id in paths:
            return paths[node_id]
        parent = parents.get(node_id)
        paths[node_id] = (
            f"{path_for(parent)}.{identifiers[node_id]}"
            if parent in node_ids
            else identifiers[node_id]
        )
        return paths[node_id]

    for node_id in sorted(node_ids, key=lambda item: identifiers.get(item, item)):
        if node_id in identifiers:
            path_for(node_id)
    return paths


def _scenario_lines(
    scenario: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
    library: ArcadiaOALibrary,
    indent: str,
) -> list[str]:
    config = library.contract.get("operational_scenario", {})
    if not config:
        return _comments(
            "UNMAPPED Arcadia Operational Scenario: no mapping declared by the library.",
            indent,
        )

    name = _clean(scenario.get("name") or scenario.get("id") or "Scenario")
    if scenario.get("valid") is False:
        lines = _comments(f"Invalid Operational Scenario omitted: {name}", indent)
        issues = scenario.get("issues", []) if isinstance(scenario.get("issues"), list) else []
        for issue in issues:
            lines += _comments(f"issue: {_clean(issue)}", indent)
        return lines

    steps = [step for step in scenario.get("steps", []) if isinstance(step, dict)]
    activity_steps = [step for step in steps if step.get("kind") == "activity"]
    if not activity_steps:
        return _comments(
            f"Operational Scenario omitted because it has no activities: {name}",
            indent,
        )

    relations = library.contract.get("relationships", {})
    interaction_relation = str(config.get("interaction_relation") or "")
    flow_mapping = relations.get(interaction_relation, {})
    if flow_mapping.get("strategy") != "flow":
        return _comments(f"UNMAPPED Operational Scenario interactions for {name}", indent)

    used: set[str] = set()
    scenario_id = _id(name, str(config.get("identifier_prefix") or "scenario"), used)
    step_ids: list[str] = []
    activity_prefix = str(config.get("activity_identifier_prefix") or "step")
    for index, step in enumerate(activity_steps, start=1):
        activity = node_by_id.get(str(step.get("activity_id") or ""), {})
        step_ids.append(
            _id(
                activity.get("name") or step.get("activity_id") or index,
                f"{activity_prefix}{index}",
                used,
            )
        )

    inputs: dict[str, list[str]] = defaultdict(list)
    outputs: dict[str, list[str]] = defaultdict(list)
    flow_rows: list[tuple[str, str, str, str, dict[str, Any]]] = []
    current = 0
    exchange_index = 0
    flow_used: set[str] = set()
    flow_prefix = str(flow_mapping.get("identifier_prefix") or "exchange")
    for step in steps:
        if step.get("kind") == "activity":
            current += 1
            continue
        if step.get("kind") != "interaction" or current < 1 or current >= len(step_ids):
            continue
        exchange_index += 1
        source_step = step_ids[current - 1]
        target_step = step_ids[current]
        out_name = f"{flow_prefix}_{exchange_index}_out"
        in_name = f"{flow_prefix}_{exchange_index}_in"
        outputs[source_step].append(out_name)
        inputs[target_step].append(in_name)
        flow_id = _id(step.get("exchange_name") or exchange_index, flow_prefix, flow_used)
        flow_rows.append((flow_id, source_step, out_name, f"{target_step}.{in_name}", step))

    usage_keyword = str(config.get("usage_keyword"))
    definition = str(config.get("definition"))
    activity_keyword = str(config.get("activity_usage_keyword"))
    activity_definition = str(config.get("activity_definition"))
    payload_definition = str(flow_mapping.get("payload_definition"))
    flow_definition = str(flow_mapping.get("definition"))

    lines = [f"{indent}{usage_keyword} {scenario_id} : {definition} {{"]
    lines += _comments(f"name: {name}", indent + "    ")
    for step, step_id in zip(activity_steps, step_ids):
        features = [
            *(f"{indent}        in item {feature} : {payload_definition};" for feature in inputs.get(step_id, [])),
            *(f"{indent}        out item {feature} : {payload_definition};" for feature in outputs.get(step_id, [])),
        ]
        if features:
            lines.append(f"{indent}    {activity_keyword} {step_id} : {activity_definition} {{")
            lines.extend(features)
            lines.append(f"{indent}    }}")
        else:
            lines.append(f"{indent}    {activity_keyword} {step_id} : {activity_definition};")
        activity = node_by_id.get(str(step.get("activity_id") or ""), {})
        lines += _comments(
            f"references model activity: {_clean(activity.get('name') or step.get('activity_id'))}",
            indent + "    ",
        )

    if config.get("sequence_strategy") == "first_then":
        lines.append("")
        lines.append(f"{indent}    first {step_ids[0]};")
        for step_id in step_ids[1:]:
            lines.append(f"{indent}    then {step_id};")

    for flow_id, source_step, out_name, target_ref, interaction in flow_rows:
        lines.append("")
        lines.append(
            f"{indent}    flow {flow_id} : {flow_definition} of {payload_definition}"
        )
        lines.append(f"{indent}        from {source_step}.{out_name}")
        lines.append(f"{indent}        to {target_ref};")
        if config.get("communication_reference_strategy") == "comment_only":
            communication = interaction.get("communication_mean")
            if isinstance(communication, dict) and _clean(communication.get("name")):
                lines += _comments(
                    "Communication Mean reference retained without additional SysML mapping: "
                    f"{_clean(communication.get('name'))}",
                    indent + "    ",
                )
    lines.append(f"{indent}}}")
    return lines


def generate_sysml_v2(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None = None,
    drafts: list[dict[str, Any]] | None = None,
    library: ArcadiaOALibrary | None = None,
) -> str:
    """Translate the source model using only mappings declared by the library bundle."""
    library = library or DEFAULT_ARCADIA_OA_LIBRARY
    contract = library.contract
    model = payload if isinstance(payload, dict) else {}
    nodes = sorted([n for n in model.get("nodes", []) if isinstance(n, dict)], key=_node_key)
    edges = sorted([e for e in model.get("edges", []) if isinstance(e, dict)], key=_edge_key)
    node_by_id = {str(node.get("id")): node for node in nodes if node.get("id") is not None}
    scenarios = [
        item
        for item in (scenarios if scenarios is not None else model.get("scenarios", []))
        if isinstance(item, dict)
    ]
    drafts = [
        item
        for item in (drafts if drafts is not None else model.get("drafts", []))
        if isinstance(item, dict)
    ]

    node_mappings = contract.get("node_types", {})
    relation_mappings = contract.get("relationships", {})
    projection = contract.get("projection", {})

    identifiers: dict[str, str] = {}
    used: set[str] = set()
    for node in nodes:
        mapping = node_mappings.get(str(node.get("type") or ""))
        if not isinstance(mapping, dict):
            continue
        node_id = str(node.get("id") or "")
        identifiers[node_id] = _id(
            node.get("name") or node_id,
            str(mapping.get("identifier_prefix") or "element"),
            used,
        )

    classified: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    explicitly_unmapped: list[dict[str, Any]] = []
    unknown_edges: list[dict[str, Any]] = []
    for edge in edges:
        mapping = relation_mappings.get(str(edge.get("type") or ""))
        if not isinstance(mapping, dict):
            unknown_edges.append(edge)
            continue
        strategy = str(mapping.get("strategy") or "")
        if strategy == "unmapped" or not _allowed_relation(edge, mapping, node_by_id):
            explicitly_unmapped.append(edge)
            continue
        classified[strategy].append((edge, mapping))

    nested_parents, nested_children, rejected_nested = _hierarchy(
        classified.get("nested_usage", []), identifiers
    )
    explicitly_unmapped.extend(rejected_nested)

    graph = model.get("graph", {}) if isinstance(model.get("graph"), dict) else {}
    model_name = _clean(graph.get("model_name") or graph.get("model") or "Operational Analysis")
    package_name = _id(model_name, "OA", set())
    package = library.package_name
    lines = [
        library.sysml_text.rstrip(),
        "",
        f"package {package_name} {{",
        f"    private import {package}::*;",
        "",
    ]
    lines += _comments(f"Generated from source model: {model_name}", "    ")
    lines += _comments(
        "Translation authority: library bundle only. No semantic fallback is permitted.",
        "    ",
    )

    unknown_nodes = [node for node in nodes if str(node.get("type") or "") not in node_mappings]
    if unknown_nodes:
        lines += ["", "    // Unmapped source nodes"]
        for node in unknown_nodes:
            lines += _comments(
                f"UNMAPPED Arcadia node {_clean(node.get('type') or 'UNKNOWN')}: "
                f"{_clean(node.get('name') or node.get('id'))}",
                "    ",
            )

    placement_ids: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        mapping = node_mappings.get(str(node.get("type") or ""))
        if isinstance(mapping, dict) and str(node.get("id") or "") in identifiers:
            placement_ids[str(mapping.get("placement") or "")].add(str(node.get("id") or ""))

    top_ids = placement_ids.get("top_level", set())
    behavior_ids = placement_ids.get("behavior", set())
    structure_ids = placement_ids.get("structure", set())
    top_paths = _paths_for(top_ids, nested_parents, identifiers)
    behavior_paths = _paths_for(behavior_ids, nested_parents, identifiers)
    structure_paths = _paths_for(structure_ids, nested_parents, identifiers)

    if top_ids:
        lines += ["", "    // Top-level library usages"]

        def emit_top(node_id: str, level: int) -> None:
            node = node_by_id[node_id]
            mapping = node_mappings[str(node.get("type"))]
            indent = "    " * level
            attrs = _characteristics(node.get("characteristics"), indent + "    ", library)
            child_ids = [child for child in nested_children.get(node_id, []) if child in top_ids]
            head = f"{indent}{mapping['usage_keyword']} {identifiers[node_id]} : {mapping['definition']}"
            if attrs or child_ids:
                lines.append(head + " {")
                lines.extend(attrs)
                for child_id in child_ids:
                    emit_top(child_id, level + 1)
                lines.append(f"{indent}}}")
            else:
                lines.append(head + ";")
            lines += _comments(f"name: {_clean(node.get('name') or node_id)}", indent)

        top_roots = sorted(
            [node_id for node_id in top_ids if nested_parents.get(node_id) not in top_ids],
            key=lambda item: identifiers.get(item, item),
        )
        for root in top_roots:
            emit_top(root, 1)

    flow_rows: list[tuple[dict[str, Any], dict[str, Any], str, str, str]] = []
    incoming: dict[str, list[tuple[str, str]]] = defaultdict(list)
    outgoing: dict[str, list[tuple[str, str]]] = defaultdict(list)
    flow_used: set[str] = set()
    for index, (edge, mapping) in enumerate(classified.get("flow", []), start=1):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in behavior_ids or target not in behavior_ids:
            explicitly_unmapped.append(edge)
            continue
        prefix = str(mapping.get("identifier_prefix") or "flow")
        out_name = f"{prefix}_{index}_out"
        in_name = f"{prefix}_{index}_in"
        payload_definition = str(mapping.get("payload_definition"))
        outgoing[source].append((out_name, payload_definition))
        incoming[target].append((in_name, payload_definition))
        flow_rows.append(
            (
                edge,
                mapping,
                _id(edge.get("name") or index, prefix, flow_used),
                out_name,
                in_name,
            )
        )

    behavior_container = projection.get("behavior_container", {})
    behavior_container_id = str(behavior_container.get("identifier") or "behavior")
    if behavior_ids or flow_rows:
        lines += [
            "",
            f"    {behavior_container.get('usage_keyword', 'action')} {behavior_container_id} {{",
        ]

        def emit_behavior(node_id: str, level: int) -> None:
            node = node_by_id[node_id]
            mapping = node_mappings[str(node.get("type"))]
            indent = "    " * level
            body = _characteristics(node.get("characteristics"), indent + "    ", library)
            body += [
                f"{indent}    in item {name} : {payload};"
                for name, payload in incoming.get(node_id, [])
            ]
            body += [
                f"{indent}    out item {name} : {payload};"
                for name, payload in outgoing.get(node_id, [])
            ]
            child_ids = [child for child in nested_children.get(node_id, []) if child in behavior_ids]
            head = f"{indent}{mapping['usage_keyword']} {identifiers[node_id]} : {mapping['definition']}"
            if body or child_ids:
                lines.append(head + " {")
                lines.extend(body)
                for child_id in child_ids:
                    emit_behavior(child_id, level + 1)
                lines.append(f"{indent}}}")
            else:
                lines.append(head + ";")
            lines += _comments(f"name: {_clean(node.get('name') or node_id)}", indent)

        behavior_roots = sorted(
            [node_id for node_id in behavior_ids if nested_parents.get(node_id) not in behavior_ids],
            key=lambda item: identifiers.get(item, item),
        )
        for root in behavior_roots:
            emit_behavior(root, 2)

        for edge, mapping, flow_id, out_name, in_name in flow_rows:
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            lines += [
                "",
                f"        flow {flow_id} : {mapping['definition']} of {mapping['payload_definition']}",
                f"            from {behavior_paths[source]}.{out_name}",
                f"            to {behavior_paths[target]}.{in_name};",
            ]
        lines.append("    }")

    performs_by_participant: dict[str, list[str]] = defaultdict(list)
    for edge, _mapping in classified.get("perform", []):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in structure_ids and target in behavior_ids:
            performs_by_participant[source].append(target)
        else:
            explicitly_unmapped.append(edge)

    references_by_owner: dict[str, list[tuple[dict[str, Any], dict[str, Any], str]]] = defaultdict(list)
    reference_used: dict[str, set[str]] = defaultdict(set)
    for edge, mapping in classified.get("reference", []):
        owner_endpoint = str(mapping.get("owner_endpoint") or "source")
        referenced_endpoint = str(mapping.get("referenced_endpoint") or "target")
        owner = str(edge.get(owner_endpoint) or "")
        target = str(edge.get(referenced_endpoint) or "")
        if owner not in structure_ids or target not in structure_ids:
            explicitly_unmapped.append(edge)
            continue
        target_name = node_by_id.get(target, {}).get("name") or target
        reference_id = _id(
            target_name,
            str(mapping.get("identifier_prefix") or "reference"),
            reference_used[owner],
        )
        references_by_owner[owner].append((edge, mapping, reference_id))

    structure_container = projection.get("structure_container", {})
    structure_container_id = str(structure_container.get("identifier") or "structure")
    connection_rows = classified.get("connection", [])
    if structure_ids or connection_rows:
        lines += [
            "",
            f"    {structure_container.get('usage_keyword', 'part')} {structure_container_id} {{",
        ]

        def emit_part(node_id: str, level: int) -> None:
            node = node_by_id[node_id]
            mapping = node_mappings[str(node.get("type"))]
            indent = "    " * level
            body = _characteristics(node.get("characteristics"), indent + "    ", library)
            for activity_id in sorted(
                set(performs_by_participant.get(node_id, [])),
                key=lambda value: behavior_paths.get(value, identifiers.get(value, value)),
            ):
                body.append(
                    f"{indent}    perform {behavior_container_id}.{behavior_paths[activity_id]};"
                )
            for _edge, ref_mapping, reference_id in references_by_owner.get(node_id, []):
                target_endpoint = str(ref_mapping.get("referenced_endpoint") or "target")
                target = str(_edge.get(target_endpoint) or "")
                body.append(
                    f"{indent}    ref {ref_mapping['usage_keyword']} {reference_id} : "
                    f"{ref_mapping['definition']} = {structure_container_id}.{structure_paths[target]};"
                )
            child_ids = [child for child in nested_children.get(node_id, []) if child in structure_ids]
            lines.append(
                f"{indent}{mapping['usage_keyword']} {identifiers[node_id]} : {mapping['definition']} {{"
            )
            lines.extend(body)
            for child_id in child_ids:
                emit_part(child_id, level + 1)
            lines.append(f"{indent}}}")
            lines += _comments(f"name: {_clean(node.get('name') or node_id)}", indent)

        structure_roots = sorted(
            [node_id for node_id in structure_ids if nested_parents.get(node_id) not in structure_ids],
            key=lambda item: identifiers.get(item, item),
        )
        for root in structure_roots:
            emit_part(root, 2)

        connection_used: set[str] = set()
        for index, (edge, mapping) in enumerate(connection_rows, start=1):
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if source not in structure_paths or target not in structure_paths:
                explicitly_unmapped.append(edge)
                continue
            connection_id = _id(
                edge.get("name") or index,
                str(mapping.get("identifier_prefix") or "connection"),
                connection_used,
            )
            lines.append(
                f"        connection {connection_id} : {mapping['definition']} "
                f"connect {structure_paths[source]} to {structure_paths[target]};"
            )
            lines += _comments(
                f"name: {_clean(edge.get('name') or connection_id)}",
                "        ",
            )
        lines.append("    }")

    def projected_ref(node_id: str) -> str | None:
        if node_id in top_paths:
            return top_paths[node_id]
        if node_id in behavior_paths:
            return f"{behavior_container_id}.{behavior_paths[node_id]}"
        if node_id in structure_paths:
            return f"{structure_container_id}.{structure_paths[node_id]}"
        return None

    allocation_rows = classified.get("allocation", [])
    if allocation_rows:
        lines += ["", "    // Allocations declared by the library translation contract"]
        for edge, mapping in allocation_rows:
            from_endpoint = str(mapping.get("from_endpoint") or "source")
            to_endpoint = str(mapping.get("to_endpoint") or "target")
            source_ref = projected_ref(str(edge.get(from_endpoint) or ""))
            target_ref = projected_ref(str(edge.get(to_endpoint) or ""))
            if not source_ref or not target_ref:
                explicitly_unmapped.append(edge)
                continue
            lines.append(f"    allocate {source_ref} to {target_ref};")

    unmapped_edges = explicitly_unmapped + unknown_edges
    if unmapped_edges:
        unique: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        for edge in unmapped_edges:
            unique[_edge_key(edge)] = edge
        lines += [
            "",
            "    // Source relations not translated because the library declares no valid SysML mapping",
        ]
        for edge in sorted(unique.values(), key=_edge_key):
            lines.extend(_unmapped_relation_comment(edge, node_by_id, "    "))

    if scenarios:
        lines += ["", "    // Operational Scenarios"]
        for scenario in sorted(
            scenarios,
            key=lambda item: (_clean(item.get("name")).casefold(), str(item.get("id") or "")),
        ):
            lines.extend(_scenario_lines(scenario, node_by_id, library, "    "))

    if drafts and contract.get("policy", {}).get("temporary_content") == "comment_only":
        lines += ["", "    // Temporary, unconfirmed source content"]
        for draft in drafts:
            lines += _comments(
                f"TEMPORARY: {_clean(draft.get('name') or draft.get('id') or 'candidate')} "
                f"[{_clean(draft.get('type') or 'Pending')}]",
                "    ",
            )

    lines.append("}")
    return "\n".join(lines).rstrip() + "\n"
