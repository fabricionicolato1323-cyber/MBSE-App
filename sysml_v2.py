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
                    type_name = (
                        scalar["integer"]
                        if isinstance(value, int)
                        else scalar["real"]
                    )
                    lines.append(
                        f"{indent}attribute {identifier} : {type_name} = "
                        f"{_num_text(value)};"
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
                type_name = (
                    scalar["integer"] if isinstance(value, int) else scalar["real"]
                )
                lines.append(
                    f"{indent}attribute {identifier} : {type_name} = "
                    f"{_num_text(value)};"
                )
            if unit and unit_strategy == "comment_only":
                lines += _comments(f"unit: {unit}", indent)
        elif kind == "text":
            value = json.dumps(_clean(item.get("value")), ensure_ascii=False)
            lines.append(
                f"{indent}attribute {identifier} : {scalar['string']} = {value};"
            )
        else:
            lines.append(f"{indent}attribute {identifier};")
            lines += _comments(
                "Characteristic value kind is not mapped by ArcadiaOA; value omitted.",
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


def _scenario_lines(
    scenario: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
    library: ArcadiaOALibrary,
    indent: str,
) -> list[str]:
    config = library.contract.get("operational_scenario", {})
    if not config:
        return _comments(
            "UNMAPPED Arcadia Operational Scenario: no mapping declared by ArcadiaOA.",
            indent,
        )

    name = _clean(scenario.get("name") or scenario.get("id") or "Scenario")
    if scenario.get("valid") is False:
        lines = _comments(f"Invalid Operational Scenario omitted: {name}", indent)
        issues = (
            scenario.get("issues", [])
            if isinstance(scenario.get("issues"), list)
            else []
        )
        for issue in issues:
            lines += _comments(f"issue: {_clean(issue)}", indent)
        return lines

    steps = [
        step
        for step in scenario.get("steps", [])
        if isinstance(step, dict)
    ]
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
        return _comments(
            f"UNMAPPED Operational Scenario interactions for {name}",
            indent,
        )

    used: set[str] = set()
    scenario_id = _id(
        name,
        str(config.get("identifier_prefix") or "scenario"),
        used,
    )
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
        if (
            step.get("kind") != "interaction"
            or current < 1
            or current >= len(step_ids)
        ):
            continue
        exchange_index += 1
        source_step = step_ids[current - 1]
        target_step = step_ids[current]
        out_name = f"{flow_prefix}_{exchange_index}_out"
        in_name = f"{flow_prefix}_{exchange_index}_in"
        outputs[source_step].append(out_name)
        inputs[target_step].append(in_name)
        flow_id = _id(
            step.get("exchange_name") or exchange_index,
            flow_prefix,
            flow_used,
        )
        flow_rows.append(
            (flow_id, source_step, out_name, f"{target_step}.{in_name}", step)
        )

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
            *(
                f"{indent}        in item {feature} : {payload_definition};"
                for feature in inputs.get(step_id, [])
            ),
            *(
                f"{indent}        out item {feature} : {payload_definition};"
                for feature in outputs.get(step_id, [])
            ),
        ]
        if features:
            lines.append(
                f"{indent}    {activity_keyword} {step_id} : "
                f"{activity_definition} {{"
            )
            lines.extend(features)
            lines.append(f"{indent}    }}")
        else:
            lines.append(
                f"{indent}    {activity_keyword} {step_id} : "
                f"{activity_definition};"
            )
        activity = node_by_id.get(str(step.get("activity_id") or ""), {})
        lines += _comments(
            f"references model activity: "
            f"{_clean(activity.get('name') or step.get('activity_id'))}",
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
            f"{indent}    flow {flow_id} : {flow_definition} of "
            f"{payload_definition}"
        )
        lines.append(f"{indent}        from {source_step}.{out_name}")
        lines.append(f"{indent}        to {target_ref};")
        if config.get("communication_reference_strategy") == "comment_only":
            communication = interaction.get("communication_mean")
            if (
                isinstance(communication, dict)
                and _clean(communication.get("name"))
            ):
                lines += _comments(
                    "Communication Mean reference retained without additional "
                    f"SysML mapping: {_clean(communication.get('name'))}",
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
    """Translate the OA model using only mappings declared by ArcadiaOA."""
    library = library or DEFAULT_ARCADIA_OA_LIBRARY
    contract = library.contract
    model = payload if isinstance(payload, dict) else {}
    nodes = sorted(
        [n for n in model.get("nodes", []) if isinstance(n, dict)],
        key=_node_key,
    )
    edges = sorted(
        [e for e in model.get("edges", []) if isinstance(e, dict)],
        key=_edge_key,
    )
    node_by_id = {
        str(node.get("id")): node
        for node in nodes
        if node.get("id") is not None
    }
    scenarios = [
        item
        for item in (
            scenarios if scenarios is not None else model.get("scenarios", [])
        )
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

    graph = model.get("graph", {}) if isinstance(model.get("graph"), dict) else {}
    model_name = _clean(
        graph.get("model_name") or graph.get("model") or "Operational Analysis"
    )
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
        "Translation authority: ArcadiaOA library bundle only. "
        "No semantic fallback is permitted.",
        "    ",
    )

    unknown_nodes = [
        node
        for node in nodes
        if str(node.get("type") or "") not in node_mappings
    ]
    if unknown_nodes:
        lines += ["", "    // Unmapped source nodes"]
        for node in unknown_nodes:
            lines += _comments(
                f"UNMAPPED Arcadia node {_clean(node.get('type') or 'UNKNOWN')}: "
                f"{_clean(node.get('name') or node.get('id'))}",
                "    ",
            )

    top_nodes = [
        node
        for node in nodes
        if isinstance(node_mappings.get(str(node.get("type") or "")), dict)
        and node_mappings[str(node.get("type"))].get("placement") == "top_level"
    ]
    if top_nodes:
        lines += ["", "    // Top-level ArcadiaOA usages"]
        for node in top_nodes:
            mapping = node_mappings[str(node.get("type"))]
            node_id = str(node.get("id") or "")
            attrs = _characteristics(
                node.get("characteristics"),
                "        ",
                library,
            )
            head = (
                f"    {mapping['usage_keyword']} {identifiers[node_id]} : "
                f"{mapping['definition']}"
            )
            if attrs:
                lines.append(head + " {")
                lines.extend(attrs)
                lines.append("    }")
            else:
                lines.append(head + ";")
            lines += _comments(
                f"name: {_clean(node.get('name') or node_id)}",
                "    ",
            )

    behavior_nodes = [
        node
        for node in nodes
        if isinstance(node_mappings.get(str(node.get("type") or "")), dict)
        and node_mappings[str(node.get("type"))].get("placement") == "behavior"
    ]
    flow_edges: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for edge in edges:
        mapping = relation_mappings.get(str(edge.get("type") or ""))
        if (
            isinstance(mapping, dict)
            and mapping.get("strategy") == "flow"
            and _allowed_relation(edge, mapping, node_by_id)
        ):
            flow_edges.append((edge, mapping))

    incoming: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    outgoing: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    flow_rows: list[
        tuple[dict[str, Any], dict[str, Any], str, str, str]
    ] = []
    flow_used: set[str] = set()
    for index, (edge, mapping) in enumerate(flow_edges, start=1):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in identifiers or target not in identifiers:
            continue
        prefix = str(mapping.get("identifier_prefix") or "flow")
        out_name = f"{prefix}_{index}_out"
        in_name = f"{prefix}_{index}_in"
        payload_definition = str(mapping.get("payload_definition"))
        outgoing[source].append((index, out_name, payload_definition))
        incoming[target].append((index, in_name, payload_definition))
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
    if behavior_nodes or flow_rows:
        lines += [
            "",
            f"    {behavior_container.get('usage_keyword', 'action')} "
            f"{behavior_container.get('identifier', 'behavior')} {{",
        ]
        for node in behavior_nodes:
            mapping = node_mappings[str(node.get("type"))]
            node_id = str(node.get("id") or "")
            body = _characteristics(
                node.get("characteristics"),
                "            ",
                library,
            )
            body += [
                f"            in item {name} : {payload};"
                for _, name, payload in incoming.get(node_id, [])
            ]
            body += [
                f"            out item {name} : {payload};"
                for _, name, payload in outgoing.get(node_id, [])
            ]
            head = (
                f"        {mapping['usage_keyword']} {identifiers[node_id]} : "
                f"{mapping['definition']}"
            )
            if body:
                lines.append(head + " {")
                lines.extend(body)
                lines.append("        }")
            else:
                lines.append(head + ";")
            lines += _comments(
                f"name: {_clean(node.get('name') or node_id)}",
                "        ",
            )
        for edge, mapping, flow_id, out_name, in_name in flow_rows:
            source = str(edge.get("source"))
            target = str(edge.get("target"))
            lines += [
                "",
                f"        flow {flow_id} : {mapping['definition']} of "
                f"{mapping['payload_definition']}",
                f"            from {identifiers[source]}.{out_name}",
                f"            to {identifiers[target]}.{in_name};",
            ]
        lines.append("    }")

    participant_nodes = [
        node
        for node in nodes
        if isinstance(node_mappings.get(str(node.get("type") or "")), dict)
        and node_mappings[str(node.get("type"))].get("placement") == "structure"
    ]
    participant_ids = {str(node.get("id")) for node in participant_nodes}
    containment_edges: list[tuple[dict[str, Any], dict[str, Any]]] = []
    perform_edges: list[tuple[dict[str, Any], dict[str, Any]]] = []
    connection_edges: list[tuple[dict[str, Any], dict[str, Any]]] = []
    explicitly_unmapped: list[dict[str, Any]] = []
    unknown_edges: list[dict[str, Any]] = []

    for edge in edges:
        mapping = relation_mappings.get(str(edge.get("type") or ""))
        if not isinstance(mapping, dict):
            unknown_edges.append(edge)
            continue
        strategy = mapping.get("strategy")
        if strategy == "unmapped":
            explicitly_unmapped.append(edge)
        elif not _allowed_relation(edge, mapping, node_by_id):
            explicitly_unmapped.append(edge)
        elif strategy == "containment":
            containment_edges.append((edge, mapping))
        elif strategy == "perform":
            perform_edges.append((edge, mapping))
        elif strategy == "connection":
            connection_edges.append((edge, mapping))

    parents: dict[str, str] = {}
    children: dict[str, list[str]] = defaultdict(list)
    for edge, _mapping in containment_edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if (
            source in participant_ids
            and target in participant_ids
            and target not in parents
        ):
            parents[target] = source
            children[source].append(target)
    for values in children.values():
        values.sort(key=lambda item: identifiers.get(item, item))

    performs_by_participant: dict[str, list[str]] = defaultdict(list)
    for edge, _mapping in perform_edges:
        performs_by_participant[str(edge.get("source") or "")].append(
            str(edge.get("target") or "")
        )

    paths: dict[str, str] = {}

    def path_for(node_id: str) -> str:
        if node_id in paths:
            return paths[node_id]
        parent = parents.get(node_id)
        paths[node_id] = (
            f"{path_for(parent)}.{identifiers[node_id]}"
            if parent in participant_ids
            else identifiers[node_id]
        )
        return paths[node_id]

    for node_id in participant_ids:
        if node_id in identifiers:
            path_for(node_id)

    structure_container = projection.get("structure_container", {})
    if participant_nodes or connection_edges:
        lines += [
            "",
            f"    {structure_container.get('usage_keyword', 'part')} "
            f"{structure_container.get('identifier', 'structure')} {{",
        ]

        def emit_part(node_id: str, level: int) -> None:
            node = node_by_id[node_id]
            mapping = node_mappings[str(node.get("type"))]
            indent = "    " * level
            lines.append(
                f"{indent}{mapping['usage_keyword']} {identifiers[node_id]} : "
                f"{mapping['definition']} {{"
            )
            lines.extend(
                _characteristics(
                    node.get("characteristics"),
                    indent + "    ",
                    library,
                )
            )
            for activity_id in sorted(
                set(performs_by_participant.get(node_id, [])),
                key=lambda value: identifiers.get(value, value),
            ):
                if activity_id in identifiers and behavior_container:
                    lines.append(
                        f"{indent}    perform "
                        f"{behavior_container.get('identifier')}."
                        f"{identifiers[activity_id]};"
                    )
            for child_id in children.get(node_id, []):
                emit_part(child_id, level + 1)
            lines.append(f"{indent}}}")
            lines.extend(
                _comments(
                    f"name: {_clean(node.get('name') or node_id)}",
                    indent,
                )
            )

        roots = sorted(
            participant_ids - set(parents),
            key=lambda item: identifiers.get(item, item),
        )
        for root in roots:
            if root in identifiers:
                emit_part(root, 2)

        connection_used: set[str] = set()
        for index, (edge, mapping) in enumerate(connection_edges, start=1):
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if source not in paths or target not in paths:
                lines.extend(
                    _unmapped_relation_comment(edge, node_by_id, "        ")
                )
                continue
            connection_id = _id(
                edge.get("name") or index,
                str(mapping.get("identifier_prefix") or "connection"),
                connection_used,
            )
            lines.append(
                f"        connection {connection_id} : {mapping['definition']} "
                f"connect {paths[source]} to {paths[target]};"
            )
            lines += _comments(
                f"name: {_clean(edge.get('name') or connection_id)}",
                "        ",
            )
        lines.append("    }")

    unmapped_edges = explicitly_unmapped + unknown_edges
    if unmapped_edges:
        lines += [
            "",
            "    // Source relations not translated because ArcadiaOA declares "
            "no SysML mapping",
        ]
        for edge in sorted(unmapped_edges, key=_edge_key):
            lines.extend(_unmapped_relation_comment(edge, node_by_id, "    "))

    if scenarios:
        lines += ["", "    // Operational Scenarios"]
        for scenario in sorted(
            scenarios,
            key=lambda item: (
                _clean(item.get("name")).casefold(),
                str(item.get("id") or ""),
            ),
        ):
            lines.extend(_scenario_lines(scenario, node_by_id, library, "    "))

    if (
        drafts
        and contract.get("policy", {}).get("temporary_content") == "comment_only"
    ):
        lines += ["", "    // Temporary, unconfirmed source content"]
        for draft in drafts:
            lines += _comments(
                f"TEMPORARY: "
                f"{_clean(draft.get('name') or draft.get('id') or 'candidate')} "
                f"[{_clean(draft.get('type') or 'Pending')}]",
                "    ",
            )

    lines.append("}")
    return "\n".join(lines).rstrip() + "\n"
