from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import defaultdict
from typing import Any

ARCADIA_OA_LIBRARY_TEXT = """package ArcadiaOA {
    part def OperationalEntity;
    part def OperationalActor :> OperationalEntity;

    action def OperationalActivity;
    item def OperationalInformation;

    flow def OperationalExchange;
    connection def CommunicationMean;

    action def OperationalScenario;
    requirement def OperationalCapability;
}"""


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


def _characteristics(values: Any, indent: str) -> list[str]:
    if not isinstance(values, list):
        return []
    used: set[str] = set()
    lines: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name")) or "Characteristic"
        kind = _clean(item.get("value_type")).casefold()
        unit = _clean(item.get("unit"))
        if kind == "range":
            for suffix, key in (("lower", "lower_bound"), ("upper", "upper_bound")):
                identifier = _id(f"{name} {suffix}", "oa_attr", used)
                value = _number(item.get(key))
                if value is None:
                    lines.append(f"{indent}attribute {identifier};")
                else:
                    scalar = "Integer" if isinstance(value, int) else "Real"
                    lines.append(
                        f"{indent}attribute {identifier} : ScalarValues::{scalar} = {_num_text(value)};"
                    )
            lines += _comments(
                f"Arcadia range {name!r}" + (f"; unit: {unit}" if unit else ""), indent
            )
            continue

        identifier = _id(name, "oa_attr", used)
        if kind == "number":
            value = _number(item.get("value"))
            if value is None:
                lines.append(f"{indent}attribute {identifier};")
            else:
                scalar = "Integer" if isinstance(value, int) else "Real"
                lines.append(
                    f"{indent}attribute {identifier} : ScalarValues::{scalar} = {_num_text(value)};"
                )
            if unit:
                lines += _comments(f"unit: {unit}", indent)
        elif kind == "text":
            text = json.dumps(_clean(item.get("value")), ensure_ascii=False)
            lines.append(f"{indent}attribute {identifier} : ScalarValues::String = {text};")
        else:
            lines.append(f"{indent}attribute {identifier};")
            lines += _comments("Unsupported Arcadia characteristic kind retained without value.", indent)
    return lines


def _node_key(node: dict[str, Any]) -> tuple[str, str, str]:
    return str(node.get("type") or ""), _clean(node.get("name")).casefold(), str(node.get("id") or "")


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(edge.get("type") or ""), str(edge.get("source") or ""),
        str(edge.get("target") or ""), str(edge.get("key") or ""),
        _clean(edge.get("name")).casefold(),
    )


def _scenario_lines(scenario: dict[str, Any], nodes: dict[str, dict[str, Any]], indent: str) -> list[str]:
    name = _clean(scenario.get("name") or scenario.get("id") or "Scenario")
    if scenario.get("valid") is False:
        lines = _comments(f"Invalid Operational Scenario omitted: {name}", indent)
        for issue in scenario.get("issues", []) if isinstance(scenario.get("issues"), list) else []:
            lines += _comments(f"issue: {_clean(issue)}", indent)
        return lines

    steps = [step for step in scenario.get("steps", []) if isinstance(step, dict)]
    activities = [step for step in steps if step.get("kind") == "activity"]
    if not activities:
        return _comments(f"Operational Scenario omitted because it has no activities: {name}", indent)

    used: set[str] = set()
    scenario_id = _id(name, "oa_scenario", used)
    step_ids: list[str] = []
    for index, step in enumerate(activities, start=1):
        activity = nodes.get(str(step.get("activity_id") or ""), {})
        step_ids.append(_id(activity.get("name") or step.get("activity_id") or index, f"oa_step{index}", used))

    inputs: dict[str, list[str]] = defaultdict(list)
    outputs: dict[str, list[str]] = defaultdict(list)
    flow_rows: list[tuple[str, str, str, str, dict[str, Any]]] = []
    current = 0
    interaction_index = 0
    flow_used: set[str] = set()
    for step in steps:
        if step.get("kind") == "activity":
            current += 1
            continue
        if step.get("kind") != "interaction" or current < 1 or current >= len(step_ids):
            continue
        interaction_index += 1
        source_step, target_step = step_ids[current - 1], step_ids[current]
        out_name = f"oa_scenario_exchange_{interaction_index}_out"
        in_name = f"oa_scenario_exchange_{interaction_index}_in"
        outputs[source_step].append(out_name)
        inputs[target_step].append(in_name)
        flow_id = _id(step.get("exchange_name") or interaction_index, "oa_scenario_exchange", flow_used)
        flow_rows.append((flow_id, source_step, out_name, f"{target_step}.{in_name}", step))

    lines = [f"{indent}action {scenario_id} : OperationalScenario {{"]
    lines += _comments(f"name: {name}", indent + "    ")
    for step, step_id in zip(activities, step_ids):
        features = [
            *(f"{indent}        in item {feature} : OperationalInformation;" for feature in inputs.get(step_id, [])),
            *(f"{indent}        out item {feature} : OperationalInformation;" for feature in outputs.get(step_id, [])),
        ]
        if features:
            lines.append(f"{indent}    action {step_id} : OperationalActivity {{")
            lines.extend(features)
            lines.append(f"{indent}    }}")
        else:
            lines.append(f"{indent}    action {step_id} : OperationalActivity;")
        activity = nodes.get(str(step.get("activity_id") or ""), {})
        lines += _comments(f"references Operational Activity: {_clean(activity.get('name') or step.get('activity_id'))}", indent + "    ")

    lines.append("")
    lines.append(f"{indent}    first {step_ids[0]};")
    for step_id in step_ids[1:]:
        lines.append(f"{indent}    then {step_id};")

    for flow_id, source_step, out_name, target_ref, interaction in flow_rows:
        lines.append("")
        lines.append(f"{indent}    flow {flow_id} : OperationalExchange of OperationalInformation")
        lines.append(f"{indent}        from {source_step}.{out_name}")
        lines.append(f"{indent}        to {target_ref};")
        communication = interaction.get("communication_mean")
        if isinstance(communication, dict) and _clean(communication.get("name")):
            lines += _comments(
                f"Communication Mean for this scenario exchange: {_clean(communication.get('name'))}",
                indent + "    ",
            )
    lines.append(f"{indent}}}")
    return lines


def generate_sysml_v2(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None = None,
    drafts: list[dict[str, Any]] | None = None,
) -> str:
    model = payload if isinstance(payload, dict) else {}
    nodes = sorted([n for n in model.get("nodes", []) if isinstance(n, dict)], key=_node_key)
    edges = sorted([e for e in model.get("edges", []) if isinstance(e, dict)], key=_edge_key)
    node_by_id = {str(node.get("id")): node for node in nodes if node.get("id") is not None}
    scenarios = [s for s in (scenarios or model.get("scenarios", [])) if isinstance(s, dict)]
    drafts = [d for d in (drafts or model.get("drafts", [])) if isinstance(d, dict)]

    identifier: dict[str, str] = {}
    used: set[str] = set()
    prefixes = {
        "OperationalCapability": "oa_capability", "OperationalEntity": "oa_entity",
        "OperationalActor": "oa_actor", "OperationalActivity": "oa_activity",
    }
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node.get("type") in prefixes:
            identifier[node_id] = _id(node.get("name") or node_id, prefixes[node["type"]], used)

    model_name = _clean(model.get("graph", {}).get("model_name") if isinstance(model.get("graph"), dict) else "")
    package_name = _id(model_name or "Operational Analysis", "OA", set())
    lines = [ARCADIA_OA_LIBRARY_TEXT, "", f"package {package_name} {{", "    private import ArcadiaOA::*;", ""]
    lines += _comments(f"Generated from Arcadia Operational Analysis model: {model_name or 'unnamed model'}", "    ")
    lines += _comments("Compatibility target: Ansys SAM SysML v2 textual import; speculative mappings are emitted as comments.", "    ")

    capabilities = [n for n in nodes if n.get("type") == "OperationalCapability"]
    if capabilities:
        lines += ["", "    // Operational Capabilities"]
        for node in capabilities:
            node_id = str(node.get("id") or "")
            attrs = _characteristics(node.get("characteristics"), "        ")
            if attrs:
                lines.append(f"    requirement {identifier[node_id]} : OperationalCapability {{")
                lines.extend(attrs)
                lines.append("    }")
            else:
                lines.append(f"    requirement {identifier[node_id]} : OperationalCapability;")
            lines += _comments(f"name: {_clean(node.get('name') or node_id)}", "    ")

    activities = [n for n in nodes if n.get("type") == "OperationalActivity"]
    exchanges = [e for e in edges if e.get("type") == "OPERATIONAL_EXCHANGE"]
    incoming: dict[str, list[tuple[int, str]]] = defaultdict(list)
    outgoing: dict[str, list[tuple[int, str]]] = defaultdict(list)
    exchange_ids: list[tuple[dict[str, Any], str, str, str]] = []
    flow_used: set[str] = set()
    for index, edge in enumerate(exchanges, start=1):
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source not in identifier or target not in identifier:
            continue
        out_name, in_name = f"oa_exchange_{index}_out", f"oa_exchange_{index}_in"
        outgoing[source].append((index, out_name))
        incoming[target].append((index, in_name))
        exchange_ids.append((edge, _id(edge.get("name") or index, "oa_exchange", flow_used), out_name, in_name))

    lines += ["", "    action oa_operationalBehavior {"]
    for node in activities:
        node_id = str(node.get("id") or "")
        body = _characteristics(node.get("characteristics"), "            ")
        body += [f"            in item {name} : OperationalInformation;" for _, name in incoming.get(node_id, [])]
        body += [f"            out item {name} : OperationalInformation;" for _, name in outgoing.get(node_id, [])]
        if body:
            lines.append(f"        action {identifier[node_id]} : OperationalActivity {{")
            lines.extend(body)
            lines.append("        }")
        else:
            lines.append(f"        action {identifier[node_id]} : OperationalActivity;")
        lines += _comments(f"name: {_clean(node.get('name') or node_id)}", "        ")
    for edge, flow_id, out_name, in_name in exchange_ids:
        source, target = str(edge.get("source")), str(edge.get("target"))
        lines += ["", f"        flow {flow_id} : OperationalExchange of OperationalInformation",
                  f"            from {identifier[source]}.{out_name}",
                  f"            to {identifier[target]}.{in_name};"]
    lines.append("    }")

    participants = [n for n in nodes if n.get("type") in {"OperationalEntity", "OperationalActor"}]
    participant_ids = {str(n.get("id")) for n in participants}
    parents: dict[str, str] = {}
    children: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.get("type") == "CONTAINS" and str(edge.get("source")) in participant_ids and str(edge.get("target")) in participant_ids:
            child, parent = str(edge.get("target")), str(edge.get("source"))
            if child not in parents:
                parents[child] = parent
                children[parent].append(child)
    for values in children.values():
        values.sort(key=lambda item: identifier.get(item, item))

    performer: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.get("type") == "PERFORMS":
            performer[str(edge.get("source"))].append(str(edge.get("target")))

    paths: dict[str, str] = {}
    def path_for(node_id: str) -> str:
        if node_id in paths:
            return paths[node_id]
        parent = parents.get(node_id)
        paths[node_id] = f"{path_for(parent)}.{identifier[node_id]}" if parent in participant_ids else identifier[node_id]
        return paths[node_id]
    for node_id in participant_ids:
        path_for(node_id)

    lines += ["", "    part oa_operationalContext {"]
    def emit_part(node_id: str, level: int) -> None:
        node = node_by_id[node_id]
        indent = "    " * level
        kind = "OperationalActor" if node.get("type") == "OperationalActor" else "OperationalEntity"
        lines.append(f"{indent}part {identifier[node_id]} : {kind} {{")
        lines.extend(_characteristics(node.get("characteristics"), indent + "    "))
        for activity_id in sorted(set(performer.get(node_id, [])), key=lambda value: identifier.get(value, value)):
            if activity_id in identifier:
                lines.append(f"{indent}    perform oa_operationalBehavior.{identifier[activity_id]};")
        for child_id in children.get(node_id, []):
            emit_part(child_id, level + 1)
        lines.append(f"{indent}}}")
        lines.extend(_comments(f"name: {_clean(node.get('name') or node_id)}", indent))
    roots = sorted(participant_ids - set(parents), key=lambda item: identifier.get(item, item))
    for root in roots:
        emit_part(root, 2)

    cm_used: set[str] = set()
    for index, edge in enumerate([e for e in edges if e.get("type") == "COMMUNICATION_MEAN"], start=1):
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source not in paths or target not in paths:
            lines += _comments(f"Communication Mean {_clean(edge.get('name'))!r} omitted: endpoint is not a confirmed participant.", "        ")
            continue
        cm_id = _id(edge.get("name") or index, "oa_communication", cm_used)
        lines.append(f"        connection {cm_id} : CommunicationMean connect {paths[source]} to {paths[target]};")
        lines += _comments(f"name: {_clean(edge.get('name') or 'Communication')}", "        ")
    lines.append("    }")

    uncertain = {"SUPPORTS_CAPABILITY", "LOCATED_IN", "DECOMPOSES"}
    uncertain_edges = [edge for edge in edges if edge.get("type") in uncertain]
    if uncertain_edges:
        lines += ["", "    // Arcadia relations awaiting a frozen SysML/SAM mapping"]
        for edge in uncertain_edges:
            source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
            source_name = _clean(node_by_id.get(source, {}).get("name") or source)
            target_name = _clean(node_by_id.get(target, {}).get("name") or target)
            lines += _comments(f"{edge.get('type')}: {source_name} -> {target_name}", "    ")

    if scenarios:
        lines += ["", "    // Operational Scenarios"]
        for scenario in sorted(scenarios, key=lambda item: (_clean(item.get("name")).casefold(), str(item.get("id") or ""))):
            lines.extend(_scenario_lines(scenario, node_by_id, "    "))

    if drafts:
        lines += ["", "    // Temporary, unconfirmed model content (not emitted as SysML usages)"]
        for draft in drafts:
            lines += _comments(f"TEMPORARY: {_clean(draft.get('name') or draft.get('id') or 'candidate')} [{_clean(draft.get('type') or 'Pending')}]", "    ")

    lines.append("}")
    return "\n".join(lines).rstrip() + "\n"
