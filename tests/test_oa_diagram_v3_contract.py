from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "static" / "oa_diagram.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static" / "oa_diagram.css").read_text(encoding="utf-8")


def test_containment_measurement_uses_current_seen_set_before_cycle_guard_extension():
    assert "const size = measureParticipant(id, seen);" in SCRIPT
    assert "const size = measureParticipant(id, next);" not in SCRIPT
    assert "normalizeContainmentGeometry" in SCRIPT
    assert "requiredContainerSize" in SCRIPT


def test_location_can_be_visual_enclosure_without_changing_semantic_relation():
    assert "validVisualLocation" in SCRIPT
    assert "edge.type === 'LOCATED_IN'" in SCRIPT
    assert "addParent(child.id, parent.id, 'LOCATED_IN')" in SCRIPT


def test_repeated_api_polling_does_not_rebuild_unchanged_layout():
    assert "modelSignature" in SCRIPT
    assert "state.modelSignature === nextSignature" in SCRIPT
    assert "scheduleEdgeRender" in SCRIPT
    assert "requestAnimationFrame" in SCRIPT


def test_capability_visibility_toggle_is_available_and_filters_support_edges():
    assert "oaDiagramCapabilitiesToggle" in SCRIPT
    assert "Capabilities: ${state.showCapabilities ? 'On' : 'Off'}" in SCRIPT
    assert "edge.type === 'SUPPORTS_CAPABILITY'" in SCRIPT
    assert "setCapabilitiesVisible" in SCRIPT


def test_exchange_routes_through_ports_when_communication_mean_is_associated():
    assert "exchange_refs" in SCRIPT
    assert "resolveCommunication" in SCRIPT
    assert "renderRoutedExchange" in SCRIPT
    assert "source-segment" in SCRIPT
    assert "target-segment" in SCRIPT
    assert "direct-exchange" in SCRIPT
    assert "port.textContent = 'P'" in SCRIPT


def test_diagram_uses_separate_layers_for_containers_edges_leaves_and_ports():
    for token in (
        "oaDiagramContainers",
        "oaDiagramEdges",
        "oaDiagramNodes",
        "oaDiagramPorts",
    ):
        assert token in SCRIPT
    assert ".oa-diagram-containers" in STYLE
    assert ".oa-diagram-edges" in STYLE
    assert ".oa-diagram-nodes" in STYLE
    assert ".oa-diagram-ports" in STYLE


def test_capella_compatible_operational_analysis_color_tokens_are_defined():
    expected = {
        "--oa-entity-fill: #e9e9da",
        "--oa-actor-fill: #f2f1e7",
        "--oa-activity-fill: #f6d66f",
        "--oa-capability-fill: #e8c89d",
        "--oa-port-border: #3478ae",
    }
    for token in expected:
        assert token in STYLE
