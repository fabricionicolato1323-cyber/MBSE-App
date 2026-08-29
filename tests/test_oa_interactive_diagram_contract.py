from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOADER = (ROOT / "static" / "model_relationships.js").read_text(encoding="utf-8")
SCRIPT = (ROOT / "static" / "oa_diagram.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static" / "oa_diagram.css").read_text(encoding="utf-8")


def test_diagram_assets_are_loaded_and_markup_is_installed():
    assert "oa_diagram.css" in LOADER
    assert "oa_diagram.js" in LOADER
    assert "installMarkup" in SCRIPT
    assert "oaDiagramViewport" in SCRIPT
    assert "oaDiagramEdges" in SCRIPT


def test_diagram_supports_click_selection_and_future_scenario_mode():
    assert "oa:diagram-selection-change" in SCRIPT
    assert "setMode" in SCRIPT
    assert "scenario" in SCRIPT
    assert "dataset.oaSelectKey" in SCRIPT


def test_diagram_supports_drag_resize_zoom_pan_and_layout_persistence():
    for token in (
        "pointerdown",
        "beginMove",
        "beginResize",
        "beginPan",
        "function zoom(",
        "fitView",
        "localStorage",
    ):
        assert token in SCRIPT


def test_actor_entity_containment_rule_is_enforced_in_diagram():
    assert "validContainment" in SCRIPT
    assert "parent.type === 'OperationalActor'" in SCRIPT
    assert "child.type === 'OperationalActor'" in SCRIPT
    assert "Operational Actors cannot contain Operational Entities" in SCRIPT


def test_ports_and_communication_means_have_distinct_visual_contract():
    assert "oa-diagram-port" in STYLE
    assert "--oa-communication-stroke: 5px" in STYLE
    assert ".oa-diagram-edge.communication-mean" in STYLE
    assert "COMMUNICATION_MEAN" in SCRIPT
    assert "port.textContent = 'P'" in SCRIPT
