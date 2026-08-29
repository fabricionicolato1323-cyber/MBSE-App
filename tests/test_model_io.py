import pytest

from model_io import (
    ModelFileError,
    graph_from_model_payload,
    prepare_model_export,
    validate_model_payload,
)


def sample_model():
    return {
        "directed": True,
        "multigraph": True,
        "graph": {"model": "Arcadia Operational Analysis"},
        "nodes": [
            {"id": "g1", "type": "OperationalCapability", "name": "Protect area"},
            {
                "id": "p1",
                "type": "OperationalActor",
                "name": "Operator",
                "nature": "human_individual",
                "expects_activity": True,
            },
            {"id": "a1", "type": "OperationalActivity", "name": "Monitor area"},
        ],
        "edges": [
            {"source": "p1", "target": "a1", "key": 0, "type": "PERFORMS"},
            {"source": "a1", "target": "g1", "key": 0, "type": "SUPPORTS_CAPABILITY"},
        ],
    }


def test_valid_model_round_trips_to_multidigraph():
    payload = validate_model_payload(sample_model())
    graph = graph_from_model_payload(payload)
    assert graph.number_of_nodes() == 3
    assert graph.number_of_edges() == 2
    assert graph.nodes["a1"]["name"] == "Monitor area"


def test_export_adds_model_name_and_format_metadata():
    payload = prepare_model_export(sample_model(), "Perimeter protection")
    assert payload["graph"]["model_name"] == "Perimeter protection"
    assert payload["graph"]["mbse_app_format"] == "mbse-app-operational-analysis"
    assert payload["graph"]["mbse_app_version"] == 1


def test_invalid_relation_is_rejected():
    payload = sample_model()
    payload["edges"].append(
        {"source": "g1", "target": "a1", "key": 0, "type": "PERFORMS"}
    )
    with pytest.raises(ModelFileError):
        validate_model_payload(payload)
