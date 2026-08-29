from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = (ROOT / "static" / "oa_diagram_v2_state.js").read_text(encoding="utf-8")
RENDER = (ROOT / "static" / "oa_diagram_v2_render.js").read_text(encoding="utf-8")
INTERACTION = (ROOT / "static" / "oa_diagram_v2_interaction.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static" / "oa_diagram_capella.css").read_text(encoding="utf-8")
LOADER = (ROOT / "static" / "model_relationships.js").read_text(encoding="utf-8")


def test_contract_targets_the_assets_loaded_by_the_application():
    assert "oa_diagram_v2_interaction.js" in LOADER
    assert "oa_diagram_capella.css" in LOADER


def test_containment_measurement_uses_current_seen_set_before_cycle_guard_extension():
    assert "const size = measureParticipant(id, seen);" in STATE
    assert "const size = measureParticipant(id, next); put(id" not in STATE
    assert "normalizeContainmentGeometry" in STATE
    assert "minimumContainerDimensions" in STATE


def test_location_can_be_visual_enclosure_without_changing_semantic_relation():
    assert "validVisualLocation" in STATE
    assert "edge.type === 'LOCATED_IN'" in STATE
    assert "addParent(child.id, parent.id, 'LOCATED_IN')" in STATE


def test_repeated_api_polling_does_not_rebuild_unchanged_layout():
    assert "signatureForModel" in STATE
    assert "state.modelSignature === nextSignature" in INTERACTION
    assert "scheduleEdgeRender" in INTERACTION
    assert "requestAnimationFrame" in INTERACTION


def test_capability_visibility_toggle_is_available_and_filters_support_edges():
    assert "oaDiagramCapabilitiesToggle" in RENDER
    assert "Capabilities: ${state.showCapabilities ? 'On' : 'Off'}" in RENDER
    assert "edge.type === 'SUPPORTS_CAPABILITY'" in RENDER
    assert "setCapabilitiesVisible" in INTERACTION


def test_exchange_routes_through_ports_when_communication_mean_is_associated():
    assert "exchange_refs" in RENDER
    assert "communicationForExchange" in RENDER
    assert "renderExchangeThroughCommunication" in RENDER
    assert "source-segment" in RENDER
    assert "target-segment" in RENDER
    assert "direct-exchange" in RENDER
    assert "port.textContent = 'P'" in RENDER


def test_participant_containers_are_below_edges_and_leaf_blocks_are_above_edges():
    assert ".oa-diagram-edges { z-index:10" in STYLE
    assert ".oa-diagram-nodes { z-index:auto" in STYLE
    assert ".oa-diagram-node.participant-container { z-index:5" in STYLE
    assert ".oa-diagram-node.leaf-node { z-index:20" in STYLE
    assert ".oa-diagram-ports { z-index:40" in STYLE


def test_live_canvas_does_not_show_instructional_placeholder():
    assert ".oa-diagram-empty { display:none!important; }" in STYLE


def test_capella_compatible_operational_analysis_color_tokens_are_defined():
    expected = {
        "--oa-structural-fill-top: #f4f4ed",
        "--oa-structural-fill-bottom: #dedfce",
        "--oa-activity-fill-top: #ffe99a",
        "--oa-activity-fill-bottom: #f4cf65",
        "--oa-capability-fill-top: #f6e2cb",
        "--oa-capability-fill-bottom: #e8c69f",
    }
    for token in expected:
        assert token in STYLE
