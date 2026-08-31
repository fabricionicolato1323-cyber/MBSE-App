from __future__ import annotations

import json
from typing import Any, Iterable


class ExchangeTransportError(ValueError):
    """Raised when an Operational Exchange transport assignment is ambiguous or inconsistent."""


def relationship_identity(edge: dict[str, Any]) -> str:
    """Return the stable source-model identity used for relationship ownership references."""
    explicit = str(edge.get("id") or "").strip()
    if explicit:
        return f"id:{explicit}"
    identity = [
        str(edge.get("type") or ""),
        str(edge.get("source") or ""),
        str(edge.get("target") or ""),
        edge.get("key", 0),
    ]
    return "edge:" + json.dumps(identity, ensure_ascii=False, separators=(",", ":"), default=str)


def _exchange_signature(edge: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(edge.get("source") or ""),
        str(edge.get("target") or ""),
        str(edge.get("name") or "").strip().casefold(),
    )


def _ref_matches_exchange(reference: dict[str, Any], exchange: dict[str, Any]) -> bool:
    source, target, name = _exchange_signature(exchange)
    return (
        str(reference.get("source_activity_id") or "") == source
        and str(reference.get("target_activity_id") or "") == target
        and str(reference.get("exchange_name") or "").strip().casefold() == name
    )


def _communication_matches_participants(
    communication: dict[str, Any],
    first: str,
    second: str,
) -> bool:
    source = str(communication.get("source") or "")
    target = str(communication.get("target") or "")
    return (source == first and target == second) or (source == second and target == first)


def _legacy_transport_candidates(
    edges: list[dict[str, Any]],
    exchange: dict[str, Any],
) -> list[dict[str, Any]]:
    """Infer an old implicit assignment only when exactly the same topology supports it.

    Older MBSE-App models predate ``exchange_refs``. The diagram already preserves
    their historical meaning by treating the single Communication Mean between the
    source/target performers as the carrier. SysML/SAM must use the same rule so all
    projections represent the same confirmed model. This is read-only inference;
    the source model is not rewritten here.
    """
    source_activity = str(exchange.get("source") or "")
    target_activity = str(exchange.get("target") or "")
    source_performers = {
        str(edge.get("source") or "")
        for edge in edges
        if str(edge.get("type") or "") == "PERFORMS"
        and str(edge.get("target") or "") == source_activity
    }
    target_performers = {
        str(edge.get("source") or "")
        for edge in edges
        if str(edge.get("type") or "") == "PERFORMS"
        and str(edge.get("target") or "") == target_activity
    }
    if not source_performers or not target_performers:
        return []

    candidates: dict[str, dict[str, Any]] = {}
    for communication in edges:
        if str(communication.get("type") or "") != "COMMUNICATION_MEAN":
            continue
        for first in source_performers:
            for second in target_performers:
                if first == second:
                    continue
                if _communication_matches_participants(communication, first, second):
                    candidates[relationship_identity(communication)] = communication
    return list(candidates.values())


def resolve_exchange_transport(
    edges: Iterable[dict[str, Any]],
    exchange: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve the Communication Mean usage carrying one Operational Exchange usage.

    Definitions stay independent. This resolver only determines the owner of the
    concrete FlowConnectionUsage. Explicit ``exchange_refs`` always win. For a
    legacy model without those refs, one unique Communication Mean between the two
    activity performers is accepted as the historical implicit assignment. An
    explicitly unassigned exchange remains owned by the operational behavior
    container.
    """
    if str(exchange.get("type") or "") != "OPERATIONAL_EXCHANGE":
        return None

    edge_rows = [edge for edge in edges if isinstance(edge, dict)]
    assignment = str(exchange.get("communication_assignment") or "").strip().casefold()
    if assignment == "none":
        return None

    matches: list[dict[str, Any]] = []
    for edge in edge_rows:
        if str(edge.get("type") or "") != "COMMUNICATION_MEAN":
            continue
        refs = edge.get("exchange_refs")
        if not isinstance(refs, list):
            continue
        if any(
            isinstance(reference, dict) and _ref_matches_exchange(reference, exchange)
            for reference in refs
        ):
            matches.append(edge)

    if len(matches) > 1:
        raise ExchangeTransportError(
            f"Operational Exchange {exchange.get('name')!r} is associated with more than one "
            "Communication Mean. Resolve the duplicate assignment before synchronization."
        )
    if matches:
        return matches[0]

    legacy_matches = _legacy_transport_candidates(edge_rows, exchange)
    if len(legacy_matches) == 1:
        return legacy_matches[0]
    if len(legacy_matches) > 1 and assignment == "assigned":
        raise ExchangeTransportError(
            f"Operational Exchange {exchange.get('name')!r} is marked assigned but its legacy "
            "Communication Mean is ambiguous. Add an explicit communication association before "
            "synchronization."
        )
    if assignment == "assigned":
        raise ExchangeTransportError(
            f"Operational Exchange {exchange.get('name')!r} is marked assigned but no matching "
            "Communication Mean exchange_refs entry or unique legacy carrier exists."
        )
    return None


def transport_owner_record(
    edges: Iterable[dict[str, Any]],
    exchange: dict[str, Any],
) -> dict[str, Any]:
    medium = resolve_exchange_transport(edges, exchange)
    if medium is None:
        return {
            "owner_kind": "behavior",
            "owner_relationship_id": None,
            "owner_name": "oa_operationalBehavior",
        }
    return {
        "owner_kind": "communication_mean",
        "owner_relationship_id": relationship_identity(medium),
        "owner_name": str(medium.get("name") or "Communication Mean"),
    }
