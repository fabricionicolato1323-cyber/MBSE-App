from __future__ import annotations

import inspect

import sam_full_projection
from sam_full_projection import analyze_sam_projection, generate_sam_sysml_v2


def sample_model():
    return {
        "graph": {"model_name": "Generic operation"},
        "nodes": [
            {"id": "cap", "type": "OperationalCapability", "name": "Maintain safe operation"},
            {"id": "entity", "type": "OperationalEntity", "name": "Operations Center"},
            {"id": "actor", "type": "OperationalActor", "name": "Operator"},
            {"id": "a1", "type": "OperationalActivity", "name": "Observe condition"},
            {"id": "a2", "type": "OperationalActivity", "name": "Authorize passage"},
        ],
        "edges": [
            {"source": "entity", "target": "actor", "type": "CONTAINS"},
            {"source": "actor", "target": "a1", "type": "PERFORMS"},
            {"source": "entity", "target": "a2", "type": "PERFORMS"},
            {"source": "a1", "target": "a2", "type": "OPERATIONAL_EXCHANGE", "name": "Authorization request"},
            {"source": "a1", "target": "cap", "type": "SUPPORTS_CAPABILITY"},
            {"source": "actor", "target": "entity", "type": "COMMUNICATION_MEAN", "name": "Voice channel"},
        ],
    }


def sample_scenarios():
    return [{
        "id": "scenario",
        "name": "Nominal scenario",
        "valid": True,
        "steps": [
            {"kind": "activity", "activity_id": "a1"},
            {"kind": "interaction", "exchange_name": "Authorization request"},
            {"kind": "activity", "activity_id": "a2"},
        ],
    }]


def test_analysis_uses_performs_as_activity_ownership_and_ignores_communication_mean():
    analysis = analyze_sam_projection(sample_model(), scenarios=sample_scenarios())
    assert analysis.ready
    assert analysis.effective_performer["a1"] == "actor"
    assert analysis.effective_performer["a2"] == "entity"
    assert len(analysis.ignored_edges) == 1
    assert analysis.ignored_edges[0]["type"] == "COMMUNICATION_MEAN"


def test_text_matches_sam_reference_package_shape():
    text = generate_sam_sysml_v2(sample_model(), scenarios=sample_scenarios())
    assert "package Arcadia_OA_libray" in text
    assert "package Arcadia_OA" in text
    assert "package Structure" in text
    assert "package Requirements" in text
    assert "package Scenarios" in text
    assert "part 'Operator' : Arcadia_OA_libray::'Operational Actor'" in text
    assert "action 'Observe condition' : Arcadia_OA_libray::'Operational Activity'" in text
    assert "flow 'Authorization request' : Arcadia_OA_libray::'Operational Iteration'" in text
    assert "allocation allocate Structure::" in text
    assert "perform action 'performaction Observe condition' ::> Structure::" in text
    assert "transition" in text


def test_model_communication_mean_is_not_projected():
    text = generate_sam_sysml_v2(sample_model(), scenarios=sample_scenarios())
    assert "Voice channel" not in text
    assert "connection 'Voice channel'" not in text
    assert "interface def 'Communication Mean'" in text


def test_level_crossing_example_is_not_hardcoded_in_projection_module():
    source = inspect.getsource(sam_full_projection)
    assert "Road Vehicle" not in source
    assert "Train Driver" not in source
    assert "Level Crossing" not in source
