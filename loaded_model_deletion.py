from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from operational_scenario import load_runtime_scenarios

DELETION_PREVIEW_FILE = "deletion_preview.json"
DELETION_PREVIEW_VERSION = 1


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _canonical(value: Any) -> str:
    return _clean(value).casefold()


def _edge_reference(source: str, target: str, key: Any, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "key": key,
        "type": str(data.get("type") or ""),
        "name": _clean(data.get("name")),
    }


def _edge_identity(reference: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(reference.get("source") or ""),
        str(reference.get("target") or ""),
        str(reference.get("key") if reference.get("key") is not None else ""),
        str(reference.get("type") or ""),
        _canonical(reference.get("name")),
    )


def _same_edge(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _edge_identity(left) == _edge_identity(right)


def _matches_scenario_exchange(step: dict[str, Any], edge: dict[str, Any]) -> bool:
    if step.get("kind") != "interaction" or edge.get("type") != "OPERATIONAL_EXCHANGE":
        return False
    if str(step.get("source_activity_id") or "") != str(edge.get("source") or ""):
        return False
    if str(step.get("target_activity_id") or "") != str(edge.get("target") or ""):
        return False
    edge_key = step.get("edge_key")
    if edge_key is not None and str(edge_key) != str(edge.get("key")):
        return False
    wanted_name = _canonical(step.get("exchange_name"))
    return not wanted_name or wanted_name == _canonical(edge.get("name"))


def _matches_scenario_communication(step: dict[str, Any], edge: dict[str, Any]) -> bool:
    if step.get("kind") != "interaction" or edge.get("type") != "COMMUNICATION_MEAN":
        return False
    communication = step.get("communication_mean")
    if not isinstance(communication, dict):
        return False
    if str(communication.get("source_participant_id") or "") != str(edge.get("source") or ""):
        return False
    if str(communication.get("target_participant_id") or "") != str(edge.get("target") or ""):
        return False
    edge_key = communication.get("edge_key")
    if edge_key is not None and str(edge_key) != str(edge.get("key")):
        return False
    wanted_name = _canonical(communication.get("name"))
    return not wanted_name or wanted_name == _canonical(edge.get("name"))


def _exchange_ref_matches(reference: Any, edge: dict[str, Any]) -> bool:
    if not isinstance(reference, dict) or edge.get("type") != "OPERATIONAL_EXCHANGE":
        return False
    if str(reference.get("source_activity_id") or "") != str(edge.get("source") or ""):
        return False
    if str(reference.get("target_activity_id") or "") != str(edge.get("target") or ""):
        return False
    wanted_key = reference.get("edge_key")
    if wanted_key is not None and str(wanted_key) != str(edge.get("key")):
        return False
    wanted_name = _canonical(reference.get("exchange_name"))
    return not wanted_name or wanted_name == _canonical(edge.get("name"))


def _runtime_dir(model: Any) -> Path | None:
    model_path = getattr(model, "_web_model_path", None)
    if not model_path:
        return None
    return Path(model_path).resolve().parent


def _scenario_records(model: Any) -> list[dict[str, Any]]:
    runtime_dir = _runtime_dir(model)
    if runtime_dir is not None:
        runtime = load_runtime_scenarios(runtime_dir)
        if runtime is not None:
            return runtime
    metadata = getattr(getattr(model, "graph", None), "graph", {})
    raw = metadata.get("operational_scenarios", []) if isinstance(metadata, dict) else []
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _friendly_relation(relation: str) -> str:
    return {
        "PERFORMS": "activity assignment",
        "SUPPORTS_CAPABILITY": "goal support",
        "OPERATIONAL_EXCHANGE": "interaction",
        "COMMUNICATION_MEAN": "communication mean",
        "CONTAINS": "structural containment",
        "LOCATED_IN": "location",
        "DECOMPOSES": "decomposition",
    }.get(relation, relation.replace("_", " ").lower())


def _node_name(model: Any, node_id: str) -> str:
    try:
        return _clean(model.graph.nodes[node_id].get("name") or node_id)
    except (KeyError, TypeError):
        return node_id


def _edge_label(model: Any, edge: dict[str, Any]) -> str:
    name = _clean(edge.get("name"))
    relation = _friendly_relation(str(edge.get("type") or "connection"))
    source = _node_name(model, str(edge.get("source") or ""))
    target = _node_name(model, str(edge.get("target") or ""))
    return f"{name or relation} ({source} → {target})"


def _all_edge_references(model: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source, target, key, data in model.graph.edges(keys=True, data=True):
        result.append(_edge_reference(source, target, key, data))
    return result


def _communication_edges_referencing(
    model: Any,
    exchanges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not exchanges:
        return result
    for source, target, key, data in model.graph.edges(keys=True, data=True):
        if data.get("type") != "COMMUNICATION_MEAN":
            continue
        references = data.get("exchange_refs", [])
        if not isinstance(references, list):
            continue
        if any(
            _exchange_ref_matches(reference, exchange)
            for reference in references
            for exchange in exchanges
        ):
            result.append(_edge_reference(source, target, key, data))
    return result


def _affected_scenarios(
    model: Any,
    *,
    target_node_ids: set[str],
    removed_edges: list[dict[str, Any]],
) -> list[dict[str, str]]:
    affected: list[dict[str, str]] = []
    for scenario in _scenario_records(model):
        steps = scenario.get("steps", [])
        if not isinstance(steps, list):
            continue
        hit = False
        for step in steps:
            if not isinstance(step, dict):
                continue
            activity_ids = {
                str(step.get("activity_id") or ""),
                str(step.get("source_activity_id") or ""),
                str(step.get("target_activity_id") or ""),
            }
            if target_node_ids.intersection(activity_ids):
                hit = True
                break
            if any(
                _matches_scenario_exchange(step, edge)
                or _matches_scenario_communication(step, edge)
                for edge in removed_edges
            ):
                hit = True
                break
        if hit:
            affected.append(
                {
                    "id": str(scenario.get("id") or ""),
                    "name": _clean(scenario.get("name") or scenario.get("id") or "Scenario"),
                }
            )
    return affected


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for edge in edges:
        result[_edge_identity(edge)] = edge
    return list(result.values())


def _build_preview(
    model: Any,
    *,
    target: dict[str, Any],
    target_node_ids: set[str] | None = None,
    target_edges: list[dict[str, Any]] | None = None,
    impact_node_ids: set[str] | None = None,
    impact_edges: list[dict[str, Any]] | None = None,
    removed_edges: list[dict[str, Any]] | None = None,
    effects: list[str] | None = None,
) -> dict[str, Any]:
    target_node_ids = set(target_node_ids or set())
    target_edges = _dedupe_edges(list(target_edges or []))
    impact_node_ids = set(impact_node_ids or set()) - target_node_ids
    impact_edges = [
        edge
        for edge in _dedupe_edges(list(impact_edges or []))
        if not any(_same_edge(edge, target_edge) for target_edge in target_edges)
    ]
    removed_edges = _dedupe_edges(list(removed_edges or target_edges))
    effects = list(effects or [])

    scenarios = _affected_scenarios(
        model,
        target_node_ids=target_node_ids,
        removed_edges=removed_edges,
    )
    for scenario in scenarios:
        effects.append(
            f"Scenario '{scenario['name']}' will become invalid until its path is updated."
        )

    target_tokens = [_clean(target.get("name"))]
    target_tokens.extend(_clean(edge.get("name")) for edge in target_edges if _clean(edge.get("name")))
    impact_tokens = [_node_name(model, node_id) for node_id in sorted(impact_node_ids)]
    impact_tokens.extend(_clean(edge.get("name")) for edge in impact_edges if _clean(edge.get("name")))
    impact_tokens.extend(item["name"] for item in scenarios)

    return {
        "version": DELETION_PREVIEW_VERSION,
        "active": True,
        "target": target,
        "target_node_ids": sorted(target_node_ids),
        "target_edges": target_edges,
        "impact_node_ids": sorted(impact_node_ids),
        "impact_edges": impact_edges,
        "affected_scenarios": scenarios,
        "target_tokens": list(dict.fromkeys(token for token in target_tokens if token)),
        "impact_tokens": list(dict.fromkeys(token for token in impact_tokens if token)),
        "effects": list(dict.fromkeys(effect for effect in effects if effect)),
    }


def build_node_deletion_preview(model: Any, node_id: str) -> dict[str, Any]:
    if node_id not in model.graph:
        raise ValueError("The selected model item no longer exists.")

    node = model.graph.nodes[node_id]
    target = {
        "kind": "node",
        "node_id": node_id,
        "type": str(node.get("type") or ""),
        "name": _clean(node.get("name") or node_id),
        "match_mode": "exact",
    }
    incident: list[dict[str, Any]] = []
    impact_nodes: set[str] = set()
    effects: list[str] = []

    for source, target_id, key, data in model.graph.in_edges(node_id, keys=True, data=True):
        edge = _edge_reference(source, target_id, key, data)
        incident.append(edge)
        if source != node_id:
            impact_nodes.add(source)
        effects.append(f"The {_friendly_relation(edge['type'])} '{_edge_label(model, edge)}' will be removed.")
    for source, target_id, key, data in model.graph.out_edges(node_id, keys=True, data=True):
        edge = _edge_reference(source, target_id, key, data)
        if not any(_same_edge(edge, existing) for existing in incident):
            incident.append(edge)
            if target_id != node_id:
                impact_nodes.add(target_id)
            effects.append(f"The {_friendly_relation(edge['type'])} '{_edge_label(model, edge)}' will be removed.")

    node_type = str(node.get("type") or "")
    if node_type == "OperationalActivity":
        for performer in list(impact_nodes):
            remaining = [
                target_id
                for _, target_id, data in model.graph.out_edges(performer, data=True)
                if data.get("type") == "PERFORMS" and target_id != node_id
            ]
            if not remaining and model.graph.nodes.get(performer, {}).get("type") in {
                "OperationalActor",
                "OperationalEntity",
            }:
                effects.append(f"'{_node_name(model, performer)}' will have no remaining assigned activity.")
    elif node_type in {"OperationalActor", "OperationalEntity"}:
        for _, activity_id, data in model.graph.out_edges(node_id, data=True):
            if data.get("type") != "PERFORMS":
                continue
            remaining = [
                source
                for source, _, edge_data in model.graph.in_edges(activity_id, data=True)
                if edge_data.get("type") == "PERFORMS" and source != node_id
            ]
            if not remaining:
                impact_nodes.add(activity_id)
                effects.append(f"Activity '{_node_name(model, activity_id)}' will have no remaining performer.")

    removed_exchanges = [edge for edge in incident if edge.get("type") == "OPERATIONAL_EXCHANGE"]
    referencing_communication = _communication_edges_referencing(model, removed_exchanges)
    for edge in referencing_communication:
        impact_nodes.update({str(edge.get("source") or ""), str(edge.get("target") or "")})
        effects.append(
            f"Communication mean '{_edge_label(model, edge)}' will lose its reference to the removed interaction."
        )

    return _build_preview(
        model,
        target=target,
        target_node_ids={node_id},
        impact_node_ids=impact_nodes,
        impact_edges=[*incident, *referencing_communication],
        removed_edges=incident,
        effects=effects,
    )


def build_edge_deletion_preview(
    model: Any,
    source: str,
    target_id: str,
    key: Any,
) -> dict[str, Any]:
    try:
        data = model.graph[source][target_id][key]
    except (KeyError, TypeError) as exc:
        raise ValueError("The selected connection no longer exists.") from exc

    edge = _edge_reference(source, target_id, key, data)
    target = {
        "kind": "edge",
        "type": edge["type"],
        "name": _clean(edge.get("name")) or _friendly_relation(edge["type"]),
        "source": source,
        "target": target_id,
        "key": key,
        "match_mode": "contains",
    }
    impact_edges: list[dict[str, Any]] = []
    effects = [f"The connection '{_edge_label(model, edge)}' will be removed."]

    if edge.get("type") == "OPERATIONAL_EXCHANGE":
        referencing = _communication_edges_referencing(model, [edge])
        impact_edges.extend(referencing)
        for communication in referencing:
            effects.append(
                f"Communication mean '{_edge_label(model, communication)}' will lose its reference to this interaction."
            )

    impact_nodes = {source, target_id}
    for impact in impact_edges:
        impact_nodes.update({str(impact.get("source") or ""), str(impact.get("target") or "")})

    return _build_preview(
        model,
        target=target,
        target_edges=[edge],
        impact_node_ids=impact_nodes,
        impact_edges=impact_edges,
        removed_edges=[edge],
        effects=effects,
    )


def build_characteristic_deletion_preview(
    model: Any,
    target_record: dict[str, Any],
    position: int,
    characteristic: dict[str, Any],
) -> dict[str, Any]:
    name = _clean(characteristic.get("name") or "Characteristic")
    target = {
        "kind": "characteristic",
        "type": "Characteristic",
        "name": name,
        "match_mode": "contains",
    }
    impact_nodes: set[str] = set()
    impact_edges: list[dict[str, Any]] = []
    owner_label = str(target_record.get("label") or "model item")

    if target_record.get("kind") == "node":
        node_id = str(target_record.get("node_id") or "")
        impact_nodes.add(node_id)
        target["owner_kind"] = "node"
        target["owner_node_id"] = node_id
        target["position"] = position
    else:
        source = str(target_record.get("source") or "")
        target_id = str(target_record.get("target") or "")
        key = target_record.get("key")
        try:
            data = model.graph[source][target_id][key]
        except (KeyError, TypeError) as exc:
            raise ValueError("The characteristic owner no longer exists.") from exc
        impact_edges.append(_edge_reference(source, target_id, key, data))
        impact_nodes.update({source, target_id})
        target.update(
            {
                "owner_kind": "edge",
                "owner_source": source,
                "owner_target": target_id,
                "owner_key": key,
                "position": position,
            }
        )

    return _build_preview(
        model,
        target=target,
        impact_node_ids=impact_nodes,
        impact_edges=impact_edges,
        effects=[f"Characteristic '{name}' will be removed from {owner_label}."],
    )


def _persist_model(model: Any) -> None:
    persist = getattr(model, "_persist", None)
    if callable(persist):
        persist()


def _checkpoint(model: Any) -> None:
    checkpoint = getattr(model, "_checkpoint", None)
    if callable(checkpoint):
        checkpoint()


def _scrub_exchange_references(model: Any, removed_exchanges: list[dict[str, Any]]) -> None:
    if not removed_exchanges:
        return
    for _, _, _, data in model.graph.edges(keys=True, data=True):
        if data.get("type") != "COMMUNICATION_MEAN":
            continue
        references = data.get("exchange_refs")
        if not isinstance(references, list):
            continue
        data["exchange_refs"] = [
            reference
            for reference in references
            if not any(_exchange_ref_matches(reference, exchange) for exchange in removed_exchanges)
        ]


def delete_node(model: Any, node_id: str) -> None:
    if node_id not in model.graph:
        raise ValueError("The selected model item no longer exists.")
    removed_exchanges: list[dict[str, Any]] = []
    for source, target, key, data in list(model.graph.in_edges(node_id, keys=True, data=True)):
        if data.get("type") == "OPERATIONAL_EXCHANGE":
            removed_exchanges.append(_edge_reference(source, target, key, data))
    for source, target, key, data in list(model.graph.out_edges(node_id, keys=True, data=True)):
        if data.get("type") == "OPERATIONAL_EXCHANGE":
            edge = _edge_reference(source, target, key, data)
            if not any(_same_edge(edge, existing) for existing in removed_exchanges):
                removed_exchanges.append(edge)
    _checkpoint(model)
    model.graph.remove_node(node_id)
    _scrub_exchange_references(model, removed_exchanges)
    _persist_model(model)


def delete_edge(model: Any, source: str, target: str, key: Any) -> None:
    try:
        data = model.graph[source][target][key]
    except (KeyError, TypeError) as exc:
        raise ValueError("The selected connection no longer exists.") from exc
    edge = _edge_reference(source, target, key, data)
    _checkpoint(model)
    model.graph.remove_edge(source, target, key)
    if edge.get("type") == "OPERATIONAL_EXCHANGE":
        _scrub_exchange_references(model, [edge])
    _persist_model(model)


def delete_characteristic(
    model: Any,
    target_record: dict[str, Any],
    position: int,
) -> None:
    _checkpoint(model)
    if target_record.get("kind") == "node":
        node_id = str(target_record.get("node_id") or "")
        if node_id not in model.graph:
            raise ValueError("The characteristic owner no longer exists.")
        values = list(model.graph.nodes[node_id].get("characteristics", []))
        if position < 0 or position >= len(values):
            raise ValueError("The selected characteristic no longer exists.")
        values.pop(position)
        model.graph.nodes[node_id]["characteristics"] = values
    else:
        source = str(target_record.get("source") or "")
        target = str(target_record.get("target") or "")
        key = target_record.get("key")
        try:
            data = model.graph[source][target][key]
        except (KeyError, TypeError) as exc:
            raise ValueError("The characteristic owner no longer exists.") from exc
        values = list(data.get("characteristics", []))
        if position < 0 or position >= len(values):
            raise ValueError("The selected characteristic no longer exists.")
        values.pop(position)
        data["characteristics"] = values
    _persist_model(model)


class LoadedModelDeletionMixin:
    """Add a non-destructive deletion preview and explicit confirmation to loaded-model editing."""

    _LOADED_INTENTS = {"modify", "add", "delete"}

    def _deletion_preview_path(self) -> Path | None:
        runtime_dir = _runtime_dir(self.model)
        return runtime_dir / DELETION_PREVIEW_FILE if runtime_dir is not None else None

    def _write_deletion_preview(self, preview: dict[str, Any]) -> None:
        path = self._deletion_preview_path()
        if path is None:
            return
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    def _clear_deletion_preview(self) -> None:
        path = self._deletion_preview_path()
        if path is None:
            return
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _confirm_deletion(self, preview: dict[str, Any]) -> bool:
        self._write_deletion_preview(preview)
        target = preview.get("target", {})
        name = _clean(target.get("name") or "selected item")
        effects = preview.get("effects", []) if isinstance(preview.get("effects"), list) else []
        why = (
            "Nothing has been deleted yet. The selected item is shown in red in the model outputs; "
            "related content and side effects are shown in orange."
        )
        if effects:
            why += " " + " ".join(str(effect) for effect in effects[:4])
            if len(effects) > 4:
                why += f" {len(effects) - 4} additional side effect(s) are highlighted in the model outputs."
        try:
            return self.ask_yes_no(f"Delete '{name}'? (yes/no)", why)
        except Exception:
            self._clear_deletion_preview()
            raise

    def _delete_selected_node(self, node_id: str) -> None:
        preview = build_node_deletion_preview(self.model, node_id)
        name = preview["target"]["name"]
        if not self._confirm_deletion(preview):
            self._clear_deletion_preview()
            self.add_notice(f"Deletion cancelled. '{name}' remains in the model.")
            return
        try:
            delete_node(self.model, node_id)
            self.add_notice(f"Deleted '{name}'.")
        finally:
            self._clear_deletion_preview()

    def _delete_loaded_goal(self) -> None:
        node_id = self._select_existing_node("OperationalCapability", "goal")
        if node_id:
            self._delete_selected_node(node_id)

    def _delete_loaded_participant(self) -> None:
        participants = list(self.model.participants())
        if not participants:
            self.add_notice("No participant or context element exists yet.")
            return
        node_id = self.ask_choice(
            "Which person, organization, place, system, or other participant would you like to delete?",
            [(item, self.model.name(item)) for item in participants],
            "Choose one item. You will see all deletion effects before anything is removed.",
        )
        self._delete_selected_node(node_id)

    def _delete_loaded_activity(self) -> None:
        node_id = self._select_existing_node("OperationalActivity", "activity")
        if node_id:
            self._delete_selected_node(node_id)

    def _delete_loaded_exchange(self) -> None:
        record = self._select_loaded_exchange()
        if not record:
            return
        source, target, key, _name = record
        preview = build_edge_deletion_preview(self.model, source, target, key)
        name = preview["target"]["name"]
        if not self._confirm_deletion(preview):
            self._clear_deletion_preview()
            self.add_notice(f"Deletion cancelled. '{name}' remains in the model.")
            return
        try:
            delete_edge(self.model, source, target, key)
            self.add_notice(f"Deleted '{name}'.")
        finally:
            self._clear_deletion_preview()

    def _communication_records(self) -> list[tuple[str, str, Any, dict[str, Any]]]:
        return [
            (source, target, key, data)
            for source, target, key, data in self.model.graph.edges(keys=True, data=True)
            if data.get("type") == "COMMUNICATION_MEAN"
        ]

    def _delete_loaded_communication(self) -> None:
        records = self._communication_records()
        if not records:
            self.add_notice("No means of communication exists yet.")
            return
        selected = self.ask_choice(
            "Which means of communication would you like to delete?",
            [
                (
                    f"communication:{index}",
                    f"{_clean(data.get('name')) or 'Communication'} "
                    f"({self.model.name(source)} ↔ {self.model.name(target)})",
                )
                for index, (source, target, _key, data) in enumerate(records)
            ],
            "Choose one connection. You will see all deletion effects before anything is removed.",
        )
        try:
            source, target, key, _data = records[int(selected.split(":", 1)[1])]
        except (IndexError, ValueError, AttributeError):
            self.add_notice("That means of communication is no longer available.")
            return
        preview = build_edge_deletion_preview(self.model, source, target, key)
        name = preview["target"]["name"]
        if not self._confirm_deletion(preview):
            self._clear_deletion_preview()
            self.add_notice(f"Deletion cancelled. '{name}' remains in the model.")
            return
        try:
            delete_edge(self.model, source, target, key)
            self.add_notice(f"Deleted '{name}'.")
        finally:
            self._clear_deletion_preview()

    def _delete_loaded_characteristic(self) -> None:
        records = self._existing_characteristic_records()
        if not records:
            self.add_notice("No characteristic or limit exists yet.")
            return
        selected = self.ask_choice(
            "Which characteristic or limit would you like to delete?",
            [
                (
                    f"characteristic:{index}",
                    self._characteristic_record_label(target, characteristic),
                )
                for index, (target, _position, characteristic) in enumerate(records)
            ],
            "Choose one value or limit. You will see its effects before anything is removed.",
        )
        try:
            target_record, position, characteristic = records[int(selected.split(":", 1)[1])]
        except (IndexError, ValueError, AttributeError):
            self.add_notice("That characteristic or limit is no longer available.")
            return
        preview = build_characteristic_deletion_preview(
            self.model,
            target_record,
            position,
            characteristic,
        )
        name = preview["target"]["name"]
        if not self._confirm_deletion(preview):
            self._clear_deletion_preview()
            self.add_notice(f"Deletion cancelled. '{name}' remains in the model.")
            return
        try:
            delete_characteristic(self.model, target_record, position)
            self.add_notice(f"Deleted characteristic '{name}'.")
        finally:
            self._clear_deletion_preview()

    def _run_loaded_concept_action(self, category: str, mode: str) -> None:
        if mode != "delete":
            return super()._run_loaded_concept_action(category, mode)

        handlers = {
            "goal": self._delete_loaded_goal,
            "participants": self._delete_loaded_participant,
            "activity": self._delete_loaded_activity,
            "exchange": self._delete_loaded_exchange,
            "communication": self._delete_loaded_communication,
            "characteristics": self._delete_loaded_characteristic,
        }
        handler = handlers.get(category)
        if handler is not None:
            handler()
