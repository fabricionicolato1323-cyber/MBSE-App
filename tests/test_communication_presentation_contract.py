from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_communication_presentation_assets_are_loaded():
    loader = (ROOT / "static" / "model_relationships.js").read_text(encoding="utf-8")
    assert "communication_presentation.js" in loader
    assert "communication_presentation.css" in loader
    assert "data-oa-communication-presentation-script" in loader


def test_textual_communication_is_a_hierarchy_with_explicit_carried_exchanges():
    script = (ROOT / "static" / "communication_presentation.js").read_text(encoding="utf-8")
    assert "COMMUNICATION_MEAN" in script
    assert "exchange_refs" in script
    assert "revisionTreeItem(clean(edge.name) || 'Communication method')" in script
    assert "↔" in script
    assert "exchangeLine(ref, byId)" in script
    assert "No interaction explicitly assigned" in script


def test_diagram_communication_label_shows_mean_endpoints_and_exchange_names():
    script = (ROOT / "static" / "communication_presentation.js").read_text(encoding="utf-8")
    style = (ROOT / "static" / "communication_presentation.css").read_text(encoding="utf-8")
    assert ".communication-label[data-edge-id]" in script
    assert "communication-name-line" in script
    assert "communication-endpoints-line" in script
    assert "communication-exchange-line" in script
    assert "refs.slice(0, 3)" in script
    assert ".communication-name-line" in style
    assert ".communication-endpoints-line" in style
    assert ".communication-exchange-line" in style
