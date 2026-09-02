from __future__ import annotations

from typing import Any

from graph_model import CHARACTERISTIC_NODE_TYPES, OAGraph


_INSTALLED = False


def _persist_if_supported(model: OAGraph) -> None:
    """Keep the web autosave mirror synchronized without coupling graph logic to it."""
    persist = getattr(model, "_persist", None)
    if callable(persist):
        persist()


def _replace_characteristic(
    self: OAGraph,
    node_id: str,
    index: int,
    characteristic: dict,
) -> tuple[bool, str]:
    if node_id not in self.graph:
        return False, "Model item does not exist."
    if self.graph.nodes[node_id].get("type") not in CHARACTERISTIC_NODE_TYPES:
        return False, "Characteristics are not supported for that model item."

    current = self.characteristics_for_node(node_id)
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(current):
        return False, "Characteristic does not exist."

    ok, normalized, error = self._normalize_characteristic(characteristic)
    if not ok:
        return False, error

    remaining = current[:index] + current[index + 1 :]
    if self._characteristic_duplicate(remaining, normalized["name"]):
        return False, "A characteristic with that name already exists for this item."

    self._checkpoint()
    updated = list(current)
    updated[index] = normalized
    self.graph.nodes[node_id]["characteristics"] = updated
    _persist_if_supported(self)
    return True, ""


def _replace_exchange_characteristic(
    self: OAGraph,
    source_id: str,
    target_id: str,
    edge_key: Any,
    index: int,
    characteristic: dict,
) -> tuple[bool, str]:
    try:
        data = self.graph[source_id][target_id][edge_key]
    except (KeyError, TypeError):
        return False, "Interaction does not exist."
    if data.get("type") != "OPERATIONAL_EXCHANGE":
        return False, "That connection is not an interaction."

    current = self.characteristics_for_exchange(source_id, target_id, edge_key)
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(current):
        return False, "Characteristic does not exist."

    ok, normalized, error = self._normalize_characteristic(characteristic)
    if not ok:
        return False, error

    remaining = current[:index] + current[index + 1 :]
    if self._characteristic_duplicate(remaining, normalized["name"]):
        return False, "A characteristic with that name already exists for this interaction."

    self._checkpoint()
    updated = list(current)
    updated[index] = normalized
    data["characteristics"] = updated
    _persist_if_supported(self)
    return True, ""


def install_characteristic_edit_support() -> None:
    """Add replacement operations without changing characteristic creation logic.

    The existing characteristic builders, normalizers, duplicate checks, history,
    and graph storage remain authoritative. Replacement only swaps one explicitly
    selected characteristic after the same validation used for creation.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    OAGraph.replace_characteristic = _replace_characteristic  # type: ignore[attr-defined]
    OAGraph.replace_exchange_characteristic = _replace_exchange_characteristic  # type: ignore[attr-defined]
    _INSTALLED = True
