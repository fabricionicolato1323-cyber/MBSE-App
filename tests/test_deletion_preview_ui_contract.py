from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_deletion_preview_module_is_loaded_after_sysml_renderer() -> None:
    source = (ROOT / "static" / "model_file_io.js").read_text(encoding="utf-8")
    assert ".then(() => import('./sysml_v2_render.js'))" in source
    assert ".then(() => import('./deletion_preview_ui.js'))" in source
    assert source.index("sysml_v2_render.js") < source.index("deletion_preview_ui.js")


def test_deletion_preview_uses_red_target_and_orange_impact_contract() -> None:
    source = (ROOT / "static" / "deletion_preview_ui.js").read_text(encoding="utf-8")
    assert "--oa-delete-red" in source
    assert "--oa-impact-orange" in source
    assert "Red — pending deletion" in source
    assert "Orange — affected" in source
    assert "data-node-id" in source
    assert "data-edge-id" in source
    assert "oa-sysml-deletion-line" in source
    assert "oa-sysml-impact-line" in source


def test_loaded_model_state_exposes_transient_preview_without_export_changes() -> None:
    source = (ROOT / "web_model_session.py").read_text(encoding="utf-8")
    assert 'self.runtime_dir / "deletion_preview.json"' in source
    assert 'snapshot["deletion_preview"] = preview' in source
    export_body = source.split("def export_model", 1)[1].split("def _deletion_preview_snapshot", 1)[0]
    assert "deletion_preview" not in export_body
