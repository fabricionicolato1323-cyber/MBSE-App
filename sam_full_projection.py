from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sam_reference_profile import DEFAULT_SAM_REFERENCE_PROFILE, SAMReferenceProfile


class SAMProjectionError(ValueError):
    """Raised when source semantics cannot be represented by the SAM OA profile."""


@dataclass
class SAMProjectionAnalysis:
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    scenarios: list[dict[str, Any]]
    node_by_id: dict[str, dict[str, Any]]
    classified_edges: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    ignored_edges: list[dict[str, Any]] = field(default_factory=list)
    unsupported_nodes: list[dict[str, Any]] = field(default_factory=list)
    unsupported_edges: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    participant_parent: dict[str, str] = field(default_factory=dict)
    capability_parent: dict[str, str] = field(default_factory=dict)
    activity_parent: dict[str, str] = field(default_factory=dict)
    performer_by_activity: dict[str, str] = field(default_factory=dict)
    effective_performer: dict[str, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return not (self.unsupported_nodes or self.unsupported_edges or self.errors)


def _rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _sort_node(node: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(node.get("type") or ""),
        _clean(node.get("name")).casefold(),
        str(node.get("id") or ""),
    )


def _sort_edge(edge: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(edge.get("type") or ""),
        str(edge.get("source") or ""),
        str(edge.get("target") or ""),
        str(edge.get("key") or ""),
        _clean(edge.get("name")).casefold(),
    )


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


def _record_parent(
    parents: dict[str, str],
    *,
    parent: str,
    child: str,
    label: str,
    errors: list[str],
) -> None:
    previous = parents.get(child)
    if previous is not None and previous != parent:
        errors.append(f"{label} {child!r} has more than one parent: {previous!r}, {parent!r}.")
        return
    parents[child] = parent


def _check_cycles(parents: dict[str, str], label: str, errors: list[str]) -> None:
    for start in parents:
        current = start
        seen: set[str] = set()
        while current in parents:
            if current in seen:
                errors.append(f"{label} contains a cycle involving {current!r}.")
                break
            seen.add(current)
            current = parents[current]


def analyze_sam_projection(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None = None,
    profile: SAMReferenceProfile | None = None,
) -> SAMProjectionAnalysis:
    """Normalize and validate the source graph against the declarative SAM profile."""
    profile = profile or DEFAULT_SAM_REFERENCE_PROFILE
    model = payload if isinstance(payload, dict) else {}
    nodes = sorted(_rows(model.get("nodes")), key=_sort_node)
    edges = sorted(_rows(model.get("edges")), key=_sort_edge)
    scenario_rows = _rows(scenarios if scenarios is not None else model.get("scenarios"))
    node_by_id = {
        str(node.get("id")): node
        for node in nodes
        if node.get("id") is not None and str(node.get("id"))
    }
    analysis = SAMProjectionAnalysis(
        nodes=nodes,
        edges=edges,
        scenarios=scenario_rows,
        node_by_id=node_by_id,
        classified_edges=defaultdict(list),
    )

    source_node_types = {
        "OperationalEntity",
        "OperationalActor",
        "OperationalActivity",
        "OperationalCapability",
    }
    for node in nodes:
        node_type = str(node.get("type") or "")
        if node_type not in source_node_types or not profile.projection_enabled(node_type):
            analysis.unsupported_nodes.append(
                {
                    "id": str(node.get("id") or ""),
                    "type": node_type or "UNKNOWN",
                    "name": _clean(node.get("name") or node.get("id")),
                }
            )

    for edge in edges:
        relation = str(edge.get("type") or "")
        mapping = profile.relationships.get(relation)
        source_id = str(edge.get("source") or "")
        target_id = str(edge.get("target") or "")
        if (
            not isinstance(mapping, dict)
            or source_id not in node_by_id
            or target_id not in node_by_id
            or not _allowed_relation(edge, mapping, node_by_id)
        ):
            analysis.unsupported_edges.append(
                {
                    "type": relation or "UNKNOWN",
                    "source": source_id,
                    "target": target_id,
                    "name": _clean(edge.get("name")),
                }
            )
            continue
        strategy = str(mapping.get("strategy") or "")
        if strategy == "ignore":
            analysis.ignored_edges.append(edge)
            continue
        analysis.classified_edges[strategy].append(edge)

        if relation == "CONTAINS":
            _record_parent(
                analysis.participant_parent,
                parent=source_id,
                child=target_id,
                label="Participant containment",
                errors=analysis.errors,
            )
        elif relation == "PERFORMS":
            previous = analysis.performer_by_activity.get(target_id)
            if previous is not None and previous != source_id:
                analysis.errors.append(
                    f"Operational Activity {target_id!r} has more than one performer: "
                    f"{previous!r}, {source_id!r}."
                )
            else:
                analysis.performer_by_activity[target_id] = source_id
        elif relation == "DECOMPOSES":
            source_type = str(node_by_id[source_id].get("type") or "")
            target_type = str(node_by_id[target_id].get("type") or "")
            parents = (
                analysis.activity_parent
                if source_type == target_type == "OperationalActivity"
                else analysis.capability_parent
            )
            _record_parent(
                parents,
                parent=source_id,
                child=target_id,
                label=f"{source_type} decomposition",
                errors=analysis.errors,
            )

    _check_cycles(analysis.participant_parent, "Participant containment", analysis.errors)
    _check_cycles(analysis.activity_parent, "Operational Activity decomposition", analysis.errors)
    _check_cycles(analysis.capability_parent, "Operational Capability decomposition", analysis.errors)

    resolving: set[str] = set()

    def resolve_performer(activity_id: str) -> str:
        if activity_id in analysis.effective_performer:
            return analysis.effective_performer[activity_id]
        if activity_id in resolving:
            return ""
        resolving.add(activity_id)
        direct = analysis.performer_by_activity.get(activity_id, "")
        parent = analysis.activity_parent.get(activity_id, "")
        inherited = resolve_performer(parent) if parent else ""
        if direct and inherited and direct != inherited:
            analysis.errors.append(
                f"Operational Activity {activity_id!r} is decomposed under an activity performed "
                f"by {inherited!r} but declares a different performer {direct!r}."
            )
        performer = direct or inherited
        if not performer:
            analysis.errors.append(
                f"Operational Activity {activity_id!r} has no performer and cannot be nested in Structure."
            )
        analysis.effective_performer[activity_id] = performer
        resolving.discard(activity_id)
        return performer

    activity_ids = [
        node_id
        for node_id, node in node_by_id.items()
        if node.get("type") == "OperationalActivity"
    ]
    for activity_id in activity_ids:
        resolve_performer(activity_id)

    for scenario in scenario_rows:
        if scenario.get("valid") is False:
            continue
        for step in _rows(scenario.get("steps")):
            if step.get("kind") != "activity":
                continue
            activity_id = str(step.get("activity_id") or "")
            if (
                activity_id not in node_by_id
                or node_by_id.get(activity_id, {}).get("type") != "OperationalActivity"
            ):
                analysis.errors.append(
                    f"Operational Scenario {_clean(scenario.get('name') or scenario.get('id'))!r} "
                    f"references missing activity {activity_id!r}."
                )

    analysis.classified_edges = dict(analysis.classified_edges)
    return analysis


def _quoted(value: Any) -> str:
    text = _clean(value) or "Unnamed"
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _identifier(value: Any, fallback: str = "Operational_Analysis") -> str:
    text = unicodedata.normalize("NFKD", _clean(value)).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", text)
    result = "_".join(words) or fallback
    if result[0].isdigit():
        result = "OA_" + result
    return result[:96]


def _model_name(model: dict[str, Any]) -> str:
    graph = model.get("graph", {}) if isinstance(model.get("graph"), dict) else {}
    return _clean(graph.get("model_name") or graph.get("model") or "Operational Analysis")


def _definition_ref(profile: SAMReferenceProfile, concept: str) -> str:
    name = profile.definition(concept)["sysml_name"]
    return f"{profile.exported_library_package}::{_quoted(name)}"


def _characteristic_lines(node: dict[str, Any], indent: str) -> list[str]:
    lines: list[str] = []
    used: set[str] = set()
    for index, item in enumerate(_rows(node.get("characteristics")), start=1):
        name = _clean(item.get("name")) or f"Characteristic {index}"
        key = name.casefold()
        if key in used:
            name = f"{name} {index}"
        used.add(key)
        lines.append(f"{indent}attribute {_quoted(name)};")
        payload = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        lines.append(f"{indent}// MBSE-App characteristic: {payload}")
    return lines


def _children(parents: dict[str, str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for child, parent in parents.items():
        result[parent].append(child)
    return result


def _path_map(
    node_ids: list[str],
    parents: dict[str, str],
    node_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    result: dict[str, str] = {}

    def path_for(node_id: str) -> str:
        if node_id in result:
            return result[node_id]
        parent = parents.get(node_id)
        own = _quoted(node_by_id[node_id].get("name") or node_id)
        result[node_id] = f"{path_for(parent)}.{own}" if parent in node_by_id else own
        return result[node_id]

    for node_id in node_ids:
        path_for(node_id)
    return result


def projection_paths(analysis: SAMProjectionAnalysis) -> dict[str, dict[str, str]]:
    node_by_id = analysis.node_by_id
    participant_ids = [
        node_id
        for node_id, node in node_by_id.items()
        if node.get("type") in {"OperationalEntity", "OperationalActor"}
    ]
    participant_paths = _path_map(participant_ids, analysis.participant_parent, node_by_id)

    capability_ids = [
        node_id
        for node_id, node in node_by_id.items()
        if node.get("type") == "OperationalCapability"
    ]
    capability_paths = _path_map(capability_ids, analysis.capability_parent, node_by_id)

    activity_paths: dict[str, str] = {}

    def activity_path(activity_id: str) -> str:
        if activity_id in activity_paths:
            return activity_paths[activity_id]
        own = _quoted(node_by_id[activity_id].get("name") or activity_id)
        parent = analysis.activity_parent.get(activity_id)
        if parent:
            path = f"{activity_path(parent)}.{own}"
        else:
            performer = analysis.effective_performer.get(activity_id, "")
            base = participant_paths.get(performer, _quoted(performer or "Unassigned"))
            path = f"{base}.{own}"
        activity_paths[activity_id] = path
        return path

    for activity_id in analysis.effective_performer:
        activity_path(activity_id)
    return {
        "participants": participant_paths,
        "activities": activity_paths,
        "capabilities": capability_paths,
    }


def generate_sam_sysml_v2(
    payload: Any,
    *,
    scenarios: list[dict[str, Any]] | None = None,
    drafts: list[dict[str, Any]] | None = None,
    profile: SAMReferenceProfile | None = None,
) -> str:
    """Generate the SAM-compatible complete OA projection from the source graph."""
    profile = profile or DEFAULT_SAM_REFERENCE_PROFILE
    model = payload if isinstance(payload, dict) else {}
    analysis = analyze_sam_projection(model, scenarios=scenarios, profile=profile)
    paths = projection_paths(analysis)
    node_by_id = analysis.node_by_id
    structure_cfg = profile.contract["model_structure"]
    containers = structure_cfg["containers"]
    oa_package = str(structure_cfg.get("oa_package") or "Arcadia_OA")

    lines = [
        profile.sysml_text.rstrip(),
        "",
        f"package {_identifier(_model_name(model))} {{",
        f"    package {oa_package} {{",
        f"        package {containers['structure']} {{",
    ]

    participant_children = _children(analysis.participant_parent)
    activity_children = _children(analysis.activity_parent)
    locations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in analysis.classified_edges.get("reference", []):
        locations[str(edge.get("source") or "")].append(edge)
    root_activities: dict[str, list[str]] = defaultdict(list)
    for activity_id, performer in analysis.effective_performer.items():
        if activity_id not in analysis.activity_parent and performer:
            root_activities[performer].append(activity_id)

    def emit_activity(activity_id: str, level: int) -> None:
        node = node_by_id[activity_id]
        indent = "    " * level
        body = _characteristic_lines(node, indent + "    ")
        children = sorted(
            activity_children.get(activity_id, []),
            key=lambda item: _clean(node_by_id[item].get("name")).casefold(),
        )
        head = f"{indent}action {_quoted(node.get('name') or activity_id)} : {_definition_ref(profile, 'OperationalActivity')}"
        if body or children:
            lines.append(head + " {")
            lines.extend(body)
            for child in children:
                emit_activity(child, level + 1)
            lines.append(f"{indent}}}")
        else:
            lines.append(head + ";")

    def emit_participant(node_id: str, level: int) -> None:
        node = node_by_id[node_id]
        concept = str(node.get("type") or "OperationalEntity")
        indent = "    " * level
        body = _characteristic_lines(node, indent + "    ")
        part_children = sorted(
            participant_children.get(node_id, []),
            key=lambda item: _clean(node_by_id[item].get("name")).casefold(),
        )
        activities = sorted(
            root_activities.get(node_id, []),
            key=lambda item: _clean(node_by_id[item].get("name")).casefold(),
        )
        location_edges = sorted(locations.get(node_id, []), key=_sort_edge)
        head = f"{indent}part {_quoted(node.get('name') or node_id)} : {_definition_ref(profile, concept)}"
        if body or part_children or activities or location_edges:
            lines.append(head + " {")
            lines.extend(body)
            for activity_id in activities:
                emit_activity(activity_id, level + 1)
            for edge in location_edges:
                target_id = str(edge.get("target") or "")
                target_name = node_by_id[target_id].get("name") or target_id
                target_path = paths["participants"][target_id]
                lines.append(
                    f"{indent}    ref part {_quoted('located in ' + _clean(target_name))} : "
                    f"{_definition_ref(profile, 'OperationalEntity')} = "
                    f"{containers['structure']}::{target_path};"
                )
            for child_id in part_children:
                emit_participant(child_id, level + 1)
            lines.append(f"{indent}}}")
        else:
            lines.append(head + ";")

    participant_ids = [
        node_id
        for node_id, node in node_by_id.items()
        if node.get("type") in {"OperationalEntity", "OperationalActor"}
    ]
    participant_roots = sorted(
        [node_id for node_id in participant_ids if node_id not in analysis.participant_parent],
        key=lambda item: _clean(node_by_id[item].get("name")).casefold(),
    )
    for node_id in participant_roots:
        emit_participant(node_id, 3)

    for edge in sorted(analysis.classified_edges.get("flow", []), key=_sort_edge):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        lines.extend(
            [
                "",
                f"            flow {_quoted(edge.get('name') or 'Operational Exchange')} : "
                f"{_definition_ref(profile, 'OperationalExchange')}",
                f"                from {paths['activities'][source]}",
                f"                to {paths['activities'][target]};",
            ]
        )
    lines.append("        }")

    lines.extend(["", f"        package {containers['requirements']} {{"])
    capability_children = _children(analysis.capability_parent)

    def emit_capability(node_id: str, level: int) -> None:
        node = node_by_id[node_id]
        indent = "    " * level
        children = sorted(
            capability_children.get(node_id, []),
            key=lambda item: _clean(node_by_id[item].get("name")).casefold(),
        )
        lines.append(
            f"{indent}requirement {_quoted(node.get('name') or node_id)} : "
            f"{_definition_ref(profile, 'OperationalCapability')} {{"
        )
        lines.append(f"{indent}    subject subj;")
        lines.extend(_characteristic_lines(node, indent + "    "))
        for child_id in children:
            emit_capability(child_id, level + 1)
        lines.append(f"{indent}}}")

    capability_ids = [
        node_id
        for node_id, node in node_by_id.items()
        if node.get("type") == "OperationalCapability"
    ]
    capability_roots = sorted(
        [node_id for node_id in capability_ids if node_id not in analysis.capability_parent],
        key=lambda item: _clean(node_by_id[item].get("name")).casefold(),
    )
    for node_id in capability_roots:
        emit_capability(node_id, 3)

    for edge in sorted(analysis.classified_edges.get("allocation", []), key=_sort_edge):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        lines.append(
            f"            allocation allocate {containers['structure']}::{paths['activities'][source]} "
            f"to {paths['capabilities'][target]};"
        )
    lines.append("        }")

    lines.extend(["", f"        package {containers['scenarios']} {{"])
    valid_scenarios = [item for item in analysis.scenarios if item.get("valid") is not False]
    for scenario in sorted(
        valid_scenarios,
        key=lambda item: (_clean(item.get("name")).casefold(), str(item.get("id") or "")),
    ):
        activity_steps = [
            step
            for step in _rows(scenario.get("steps"))
            if step.get("kind") == "activity"
            and str(step.get("activity_id") or "") in paths["activities"]
        ]
        name = _clean(scenario.get("name") or scenario.get("id") or "Operational Scenario")
        if not activity_steps:
            lines.append(f"            // Scenario without activity steps omitted: {name}")
            continue
        lines.append(
            f"            action {_quoted(name)} : {_definition_ref(profile, 'OperationalScenario')} {{"
        )
        step_names: list[str] = []
        used_steps: set[str] = set()
        for index, step in enumerate(activity_steps, start=1):
            activity_id = str(step.get("activity_id") or "")
            activity_name = _clean(node_by_id[activity_id].get("name") or activity_id)
            step_name = f"performaction {activity_name}"
            if step_name.casefold() in used_steps:
                step_name = f"{step_name} {index}"
            used_steps.add(step_name.casefold())
            step_names.append(step_name)
            lines.append(
                f"                perform action {_quoted(step_name)} ::> "
                f"{containers['structure']}::{paths['activities'][activity_id]};"
            )
        for before, after in zip(step_names, step_names[1:]):
            lines.extend(
                [
                    "                transition",
                    f"                    first {_quoted(before)}",
                    f"                    then {_quoted(after)};",
                ]
            )
        lines.append("            }")
    lines.append("        }")

    diagnostics: list[str] = []
    for item in analysis.unsupported_nodes:
        diagnostics.append(
            f"Unsupported node {item['type']}: {item['name'] or item['id']}"
        )
    for item in analysis.unsupported_edges:
        diagnostics.append(
            f"Unsupported relationship {item['type']}: {item['source']} -> {item['target']}"
        )
    diagnostics.extend(analysis.errors)
    if diagnostics:
        lines.extend(["", "        // Projection diagnostics"])
        for diagnostic in diagnostics:
            lines.append(f"        // {_clean(diagnostic)}")

    draft_rows = _rows(drafts if drafts is not None else model.get("drafts"))
    if draft_rows:
        lines.extend(["", "        // Temporary, unconfirmed source content"])
        for draft in draft_rows:
            lines.append(
                "        // TEMPORARY: "
                + _clean(draft.get("name") or draft.get("id") or "candidate")
            )

    lines.extend(["    }", "}"])
    return "\n".join(lines).rstrip() + "\n"
