from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_corrected_fit_uses_renderer_canvas_origin_and_is_camera_only():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    fit_source = source.split("function scheduleCorrectedFit", 1)[0]
    assert "getCanvasOrigin" in fit_source
    assert "updateBounds();" in fit_source
    assert "box.x + origin.x" in fit_source
    assert "box.y + origin.y" in fit_source
    assert "state.view =" in fit_source
    assert "applyView();" in fit_source
    assert "autoLayout(" not in fit_source
    assert "2.5" in fit_source
    assert "availableWidth / modelWidth" in fit_source
    assert "availableHeight / modelHeight" in fit_source


def test_fit_override_prevents_original_listener_from_running_twice():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    assert "stopImmediatePropagation" in source
    assert "correctedFitInstalled" in source
    assert "}, true);" in source


def test_reset_override_rebuilds_geometry_resets_ports_and_uses_corrected_fit():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    assert "function correctedResetLayout()" in source
    assert "localStorage.removeItem(storageKey())" in source
    assert "resetPortOffsets();" in source
    assert "autoLayout();" in source
    assert "render();" in source
    assert "scheduleCorrectedFit" in source
    assert "correctedResetInstalled" in source
    assert "window.oaCorrectedDiagramReset" in source


def test_detached_fit_uses_detached_viewport_without_overwriting_main_camera():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    assert "detachedPanel" in source
    assert "clientWidth" in source
    assert "clientHeight" in source
    assert "persistView && !detachedUtilityWindow" in source
    assert "firstDetachedDiagramFitDone" in source


def test_diagram_canvas_consumes_remaining_text_panel_height():
    css = (ROOT / "static" / "oa_diagram_v4.css").read_text(encoding="utf-8")
    assert "#utilityTextView.active" in css
    assert "#utilityTextView > .tab-content.active" in css
    assert "flex: 1 1 0;" in css
    assert "#utilityTextView > #diagramTab.active" in css
    assert ".oa-diagram-selection-status" in css


def test_diagram_loader_installs_fit_patch_after_interaction_module():
    loader = (ROOT / "static" / "model_relationships.js").read_text(encoding="utf-8")
    assert "oa_diagram_fit_patch.js" in loader
    assert "ensureFitPatch" in loader
    assert "afterDiagramLoaded" in loader
