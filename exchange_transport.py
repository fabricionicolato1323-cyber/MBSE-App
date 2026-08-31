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


def resolve_exchange_transport(
    edges: Iterable[dict[str, Any]],
    exchange: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve the Communication Mean usage carrying one Operational Exchange usage.

    Definitions stay independent. This resolver only determines the owner of the
    concrete FlowConnectionUsage. An explicitly unassigned exchange remains owned
    by the operational behavior container.
    """
    if str(exchange.get("type") or "") != "OPERATIONAL_EXCHANGE":
        return None

    assignment = str(exchange.get("communication_assignment") or "").strip().casefold()
    if assignment == "none":
        return None

    matches: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict) or str(edge.get("type") or "") != "COMMUNICATION_MEAN":
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
    if assignment == "assigned":
        raise ExchangeTransportError(
            f"Operational Exchange {exchange.get('name')!r} is marked assigned but no matching "
            "Communication Mean exchange_refs entry exists."
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
