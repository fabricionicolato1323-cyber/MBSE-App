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
    assert "MAX_FIT_ZOOM = 1.0" in fit_source
    assert "availableWidth / modelWidth" in fit_source
    assert "availableHeight / modelHeight" in fit_source
    assert "FIT_PADDING" in fit_source


def test_fit_override_prevents_original_listener_from_running_twice():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    assert "stopImmediatePropagation" in source
    assert "correctedFitInstalled" in source
    assert "}, true);" in source


def test_fit_hides_native_scrollbars_until_manual_camera_interaction():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "oa_diagram_v4.css").read_text(encoding="utf-8")
    assert "classList.add('is-fit-view')" in source
    assert "releaseFittedCamera" in source
    assert "pointerdown" in source
    assert "wheel" in source
    assert ".oa-diagram-viewport.is-fit-view" in css
    assert "overflow: hidden !important;" in css


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


def test_detached_diagram_reset_preserves_main_window_camera_while_sharing_geometry():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    assert "loadSaved" in source
    assert "previouslySaved" in source
    assert "detachedDiagramWindow && previouslySaved?.view" in source
    assert "state.view = previouslySaved.view" in source
    assert "state.view = resetCamera" in source


def test_only_detached_diagram_view_uses_independent_diagram_camera():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    assert "rawDetachedPanel === 'diagram'" in source
    assert "persistView && !detachedDiagramWindow" in source
    assert "firstDetachedDiagramFitDone" in source
    assert "clientWidth" in source
    assert "clientHeight" in source


def test_diagram_canvas_consumes_remaining_unified_output_height():
    css = (ROOT / "static" / "oa_diagram_v4.css").read_text(encoding="utf-8")
    assert "#diagramTab.active" in css
    assert "display: flex !important;" in css
    assert "flex: 1 1 0;" in css
    assert "overflow: hidden;" in css
    assert ".oa-diagram-selection-status" in css


def test_diagram_loader_installs_fit_patch_after_interaction_module():
    loader = (ROOT / "static" / "model_relationships.js").read_text(encoding="utf-8")
    assert "oa_diagram_fit_patch.js" in loader
    assert "ensureFitPatch" in loader
    assert "afterDiagramLoaded" in loader
