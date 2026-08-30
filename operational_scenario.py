from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

SCENARIO_METADATA_KEY = "operational_scenarios"
RUNTIME_SCENARIO_FILE = "operational_scenarios.json"
RUNTIME_SCENARIO_VERSION = 1
MAX_SCENARIOS = 200
MAX_SCENARIO_STEPS = 1000


class ScenarioError(ValueError):
    pass


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _canonical(value: Any) -> str:
    return _clean(value).casefold()


def _graph_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    graph = payload.get("graph", {})
    return dict(graph) if isinstance(graph, dict) else {}


def scenarios_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw = _graph_metadata(payload).get(SCENARIO_METADATA_KEY, [])
    if not isinstance(raw, list):
        return []
    return [copy.deepcopy(item) for item in raw if isinstance(item, dict)]


def runtime_scenario_path(runtime_dir: Path) -> Path:
    return Path(runtime_dir) / RUNTIME_SCENARIO_FILE


def load_runtime_scenarios(runtime_dir: Path) -> list[dict[str, Any]] | None:
    path = runtime_scenario_path(runtime_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    raw = payload.get("scenarios", [])
    if not isinstance(raw, list):
        return []
    return [copy.deepcopy(item) for item in raw if isinstance(item, dict)]


def write_runtime_scenarios(runtime_dir: Path, scenarios: list[dict[str, Any]]) -> None:
    path = runtime_scenario_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {
                "version": RUNTIME_SCENARIO_VERSION,
                "scenarios": scenarios,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def merge_scenarios_into_payload(
    payload: dict[str, Any],
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    merged = copy.deepcopy(payload)
    metadata = _graph_metadata(merged)
    metadata[SCENARIO_METADATA_KEY] = copy.deepcopy(scenarios)
    merged["graph"] = metadata
    return merged


def _node_types(payload: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in payload.get("nodes", []):
        if not isinstance(item, dict):
            continue
        node_id = item.get("id")
        if isinstance(node_id, str):
            result[node_id] = str(item.get("type") or "")
    return result


def _matching_edges(
    payload: dict[str, Any],
    *,
    relation: str,
    source: Any,
    target: Any,
    edge_key: Any = None,
    name: Any = "",
) -> list[dict[str, Any]]:
    expected_name = _canonical(name)
    result: list[dict[str, Any]] = []
    for item in payload.get("edges", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "") != relation:
            continue
        if item.get("source") != source or item.get("target") != target:
            continue
        if edge_key is not None and str(item.get("key")) != str(edge_key):
            continue
        if expected_name and _canonical(item.get("name")) != expected_name:
            continue
        result.append(item)
    return result


def validate_scenario_record(
    payload: dict[str, Any],
    scenario: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    node_types = _node_types(payload)
    steps = scenario.get("steps", [])

    if not _clean(scenario.get("name")):
        issues.append("Scenario name is missing.")
    if not isinstance(steps, list):
        return [*issues, "Scenario steps are malformed."]
    if len(steps) < 3:
        issues.append("A scenario needs at least two activities and one interaction.")
    if len(steps) > MAX_SCENARIO_STEPS:
        issues.append("Scenario contains too many steps.")

    expected_kind = "activity"
    previous_activity: str | None = None
    interaction_count = 0

    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            issues.append(f"Step {index} is malformed.")
            continue

        kind = str(step.get("kind") or "").strip().casefold()
        if kind != expected_kind:
            issues.append(
                f"Step {index} must be an {expected_kind}, not {kind or 'an unknown item'}."
            )
            expected_kind = "interaction" if expected_kind == "activity" else "activity"
            continue

        if kind == "activity":
            activity_id = str(step.get("activity_id") or "").strip()
            if node_types.get(activity_id) != "OperationalActivity":
                issues.append(
                    f"Step {index} references an Operational Activity that does not exist."
                )
            if previous_activity is not None:
                expected_target = str(step.get("activity_id") or "").strip()
                prior = steps[index - 2] if index >= 2 else {}
                if isinstance(prior, dict) and prior.get("kind") == "interaction":
                    if str(prior.get("target_activity_id") or "") != expected_target:
                        issues.append(
                            f"Step {index} is not the target of the preceding interaction."
                        )
            previous_activity = activity_id
            expected_kind = "interaction"
            continue

        interaction_count += 1
        source_id = str(step.get("source_activity_id") or "").strip()
        target_id = str(step.get("target_activity_id") or "").strip()
        if source_id != previous_activity:
            issues.append(
                f"Step {index} does not start at the current scenario activity."
            )
        if node_types.get(source_id) != "OperationalActivity":
            issues.append(f"Step {index} has an invalid source activity.")
        if node_types.get(target_id) != "OperationalActivity":
            issues.append(f"Step {index} has an invalid target activity.")

        edge_key = step.get("edge_key")
        exchange_name = step.get("exchange_name", "")
        matches = _matching_edges(
            payload,
            relation="OPERATIONAL_EXCHANGE",
            source=source_id,
            target=target_id,
            edge_key=edge_key,
            name=exchange_name,
        )
        if not matches:
            issues.append(f"Step {index} references an interaction that does not exist.")
        elif edge_key is None and len(matches) != 1:
            issues.append(
                f"Step {index} does not identify one interaction unambiguously."
            )

        communication = step.get("communication_mean")
        if communication is not None:
            if not isinstance(communication, dict):
                issues.append(f"Step {index} has a malformed Communication Mean reference.")
            else:
                cm_matches = _matching_edges(
                    payload,
                    relation="COMMUNICATION_MEAN",
                    source=communication.get("source_participant_id"),
                    target=communication.get("target_participant_id"),
                    edge_key=communication.get("edge_key"),
                    name=communication.get("name", ""),
                )
                if not cm_matches:
                    issues.append(
                        f"Step {index} references a Communication Mean that does not exist."
                    )

        expected_kind = "activity"

    if steps and expected_kind != "interaction":
        issues.append("A scenario must finish with an Operational Activity.")
    if interaction_count < 1:
        issues.append("A scenario needs at least one Operational Interaction.")

    return list(dict.fromkeys(issues))


def _normalize_steps(steps: Any) -> list[dict[str, Any]]:
    if not isinstance(steps, list):
        raise ScenarioError("Scenario steps must be an ordered list.")
    if len(steps) > MAX_SCENARIO_STEPS:
        raise ScenarioError("Scenario contains too many steps.")

    normalized: list[dict[str, Any]] = []
    for order, raw in enumerate(steps, start=1):
        if not isinstance(raw, dict):
            raise ScenarioError(f"Scenario step {order} is malformed.")
        kind = str(raw.get("kind") or "").strip().casefold()
        if kind == "activity":
            normalized.append(
                {
                    "order": order,
                    "kind": "activity",
                    "activity_id": str(raw.get("activity_id") or "").strip(),
                }
            )
            continue
        if kind != "interaction":
            raise ScenarioError(f"Scenario step {order} has an unsupported type.")

        item: dict[str, Any] = {
            "order": order,
            "kind": "interaction",
            "source_activity_id": str(raw.get("source_activity_id") or "").strip(),
            "target_activity_id": str(raw.get("target_activity_id") or "").strip(),
            "edge_key": raw.get("edge_key"),
            "exchange_name": _clean(raw.get("exchange_name") or "Interaction"),
        }
        if raw.get("edge_id") is not None:
            item["edge_id"] = str(raw.get("edge_id"))
        communication = raw.get("communication_mean")
        if isinstance(communication, dict):
            item["communication_mean"] = {
                "source_participant_id": str(
                    communication.get("source_participant_id") or ""
                ).strip(),
                "target_participant_id": str(
                    communication.get("target_participant_id") or ""
                ).strip(),
                "edge_key": communication.get("edge_key"),
                "name": _clean(communication.get("name") or "Communication"),
            }
        normalized.append(item)
    return normalized


def _scenario_id(name: str, existing: list[dict[str, Any]]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "scenario"
    base = f"OperationalScenario:{slug}"
    used = {str(item.get("id") or "") for item in existing}
    if base not in used:
        return base
    index = 2
    while f"{base}-{index}" in used:
        index += 1
    return f"{base}-{index}"


def create_scenario_record(
    payload: dict[str, Any],
    existing: list[dict[str, Any]],
    *,
    name: Any,
    steps: Any,
) -> dict[str, Any]:
    scenario_name = _clean(name)
    if not scenario_name:
        raise ScenarioError("Enter a scenario name before selecting its path.")
    if len(scenario_name) > 120:
        raise ScenarioError("Scenario name must be 120 characters or fewer.")
    if len(existing) >= MAX_SCENARIOS:
        raise ScenarioError("This model already contains the maximum number of scenarios.")
    if any(_canonical(item.get("name")) == _canonical(scenario_name) for item in existing):
        raise ScenarioError("A scenario with that name already exists.")

    record = {
        "id": _scenario_id(scenario_name, existing),
        "name": scenario_name,
        "steps": _normalize_steps(steps),
    }
    issues = validate_scenario_record(payload, record)
    if issues:
        raise ScenarioError(issues[0])
    return record


def scenario_snapshots(
    payload: dict[str, Any],
    scenarios: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in scenarios:
        snapshot = copy.deepcopy(item)
        issues = validate_scenario_record(payload, snapshot)
        snapshot["valid"] = not issues
        snapshot["issues"] = issues
        result.append(snapshot)
    return result
