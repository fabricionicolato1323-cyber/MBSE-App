from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

from ontology import ALLOWED_RELATIONS, NODE_TYPES, PARTICIPANT_NATURES, PARTICIPANT_TYPES

MODEL_FILE_FORMAT = "mbse-app-operational-analysis"
MODEL_FILE_VERSION = 1
MAX_MODEL_NODES = 5000
MAX_MODEL_EDGES = 20000


class ModelFileError(ValueError):
    pass


def normalize_model_name(value: str) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    if not name:
        raise ModelFileError("Enter a model name before saving.")
    if len(name) > 120:
        raise ModelFileError("Model name must be 120 characters or fewer.")
    return name


def _model_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    graph = payload.get("graph", {})
    return dict(graph) if isinstance(graph, dict) else {}


def model_name_from_payload(payload: dict[str, Any], fallback: str = "") -> str:
    metadata = _model_metadata(payload)
    name = str(metadata.get("model_name") or "").strip()
    if name:
        return name
    return re.sub(r"\s+", " ", str(fallback or "").strip())


def fallback_model_name_from_filename(filename: str) -> str:
    stem = Path(str(filename or "")).stem.strip()
    return re.sub(r"\s+", " ", stem) or "Loaded model"


def validate_model_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ModelFileError("The selected file does not contain a model object.")

    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ModelFileError("The selected file is not a supported Operational Analysis model.")
    if len(nodes) > MAX_MODEL_NODES or len(edges) > MAX_MODEL_EDGES:
        raise ModelFileError("The selected model is too large for this prototype.")

    node_types: dict[str, str] = {}
    for item in nodes:
        if not isinstance(item, dict):
            raise ModelFileError("The model contains an invalid item record.")
        node_id = item.get("id")
        node_type = str(item.get("type") or "")
        name = str(item.get("name") or "").strip()
        if not isinstance(node_id, str) or not node_id.strip():
            raise ModelFileError("Every model item must have a valid identifier.")
        if node_id in node_types:
            raise ModelFileError("The model contains duplicate item identifiers.")
        if node_type not in NODE_TYPES:
            raise ModelFileError(f"Unsupported model item type: {node_type or 'missing type'}.")
        if not name:
            raise ModelFileError("Every model item must have a name.")
        if node_type in PARTICIPANT_TYPES:
            nature = str(item.get("nature") or "unspecified")
            if nature not in PARTICIPANT_NATURES:
                raise ModelFileError(f"Unsupported participant nature: {nature}.")
        node_types[node_id] = node_type

    for item in edges:
        if not isinstance(item, dict):
            raise ModelFileError("The model contains an invalid connection record.")
        source = item.get("source")
        target = item.get("target")
        relation = str(item.get("type") or "")
        if source not in node_types or target not in node_types:
            raise ModelFileError("A model connection references an item that does not exist.")
        signature = (node_types[source], relation, node_types[target])
        if signature not in ALLOWED_RELATIONS:
            raise ModelFileError(f"Unsupported model connection: {relation or 'missing relation'}.")

    normalized = copy.deepcopy(payload)
    normalized["directed"] = True
    normalized["multigraph"] = True
    normalized["graph"] = _model_metadata(normalized)
    return normalized


def prepare_model_export(payload: Any, model_name: str) -> dict[str, Any]:
    normalized = validate_model_payload(payload)
    name = normalize_model_name(model_name)
    metadata = _model_metadata(normalized)
    metadata["model"] = metadata.get("model") or "Arcadia Operational Analysis"
    metadata["model_name"] = name
    metadata["mbse_app_format"] = MODEL_FILE_FORMAT
    metadata["mbse_app_version"] = MODEL_FILE_VERSION
    normalized["graph"] = metadata
    return normalized


def graph_from_model_payload(payload: Any) -> nx.MultiDiGraph:
    normalized = validate_model_payload(payload)
    graph = json_graph.node_link_graph(normalized, edges="edges")
    if not isinstance(graph, nx.MultiDiGraph):
        graph = nx.MultiDiGraph(graph)
    graph.graph.setdefault("model", "Arcadia Operational Analysis")
    return graph
