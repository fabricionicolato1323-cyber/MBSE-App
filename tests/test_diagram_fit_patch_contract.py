from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_corrected_fit_uses_renderer_canvas_origin_and_is_camera_only():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    assert "getCanvasOrigin" in source
    assert "updateBounds();" in source
    assert "box.x + origin.x" in source
    assert "box.y + origin.y" in source
    assert "state.view =" in source
    assert "applyView();" in source
    assert "autoLayout" not in source


def test_fit_override_prevents_original_listener_from_running_twice():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    assert "stopImmediatePropagation" in source
    assert "correctedFitInstalled" in source
    assert "}, true);" in source


def test_detached_fit_uses_detached_viewport_without_overwriting_main_camera():
    source = (ROOT / "static" / "oa_diagram_fit_patch.js").read_text(encoding="utf-8")
    assert "detachedPanel" in source
    assert "clientWidth" in source
    assert "clientHeight" in source
    assert "persistView && !detachedUtilityWindow" in source
    assert "firstDetachedDiagramFitDone" in source


def test_diagram_loader_installs_fit_patch_after_interaction_module():
    loader = (ROOT / "static" / "model_relationships.js").read_text(encoding="utf-8")
    assert "oa_diagram_fit_patch.js" in loader
    assert "ensureFitPatch" in loader
    assert "afterDiagramLoaded" in loader
