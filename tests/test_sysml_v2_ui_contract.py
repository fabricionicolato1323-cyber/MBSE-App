from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SysMLV2UIContractTests(unittest.TestCase):
    def test_sysml_renderer_is_loaded(self) -> None:
        source = (ROOT / "static" / "model_file_io.js").read_text(encoding="utf-8")
        self.assertIn("import('./sysml_v2_render.js')", source)

    def test_renderer_uses_server_generated_level1_text(self) -> None:
        source = (ROOT / "static" / "sysml_v2_render.js").read_text(encoding="utf-8")
        self.assertIn("model?.sysml_v2_level1", source)
        self.assertIn("model?.sysml_v2", source)
        self.assertIn("Generated SysML V2 text", source)
        self.assertIn("Level 1 · Model", source)
        self.assertIn("Level 2 · Views", source)
        self.assertIn("SAM not synchronized", source)
        self.assertIn("Export Level 1 .sysml", source)

    def test_level1_requires_change_set_review_and_explicit_confirmation(self) -> None:
        source = (ROOT / "static" / "sysml_v2_render.js").read_text(encoding="utf-8")
        self.assertIn("Review / Sync with SAM", source)
        self.assertIn("Change Set", source)
        self.assertIn("CREATE", source)
        self.assertIn("UPDATE", source)
        self.assertIn("DELETE", source)
        self.assertIn("/api/sam/level1/plan", source)
        self.assertIn("window.confirm", source)
        self.assertIn("/api/sam/level1/send", source)
        self.assertIn("snapshot_digest", source)
        self.assertIn("confirm: true", source)
        self.assertIn("No write has occurred yet", source)

    def test_level1c_review_shows_relationship_delta_and_details(self) -> None:
        source = (ROOT / "static" / "sysml_v2_render.js").read_text(encoding="utf-8")
        self.assertIn("relationshipChangeDetails", source)
        self.assertIn("plan.relationship_creates", source)
        self.assertIn("plan.relationship_updates", source)
        self.assertIn("plan.relationship_deletes", source)
        self.assertIn("`RELATIONSHIPS\\n${deltaText(relationshipDelta)}", source)
        self.assertNotIn("`RELATIONSHIPS: unchanged\\n`", source)

    def test_noop_plan_does_not_post_a_write(self) -> None:
        source = (ROOT / "static" / "sysml_v2_render.js").read_text(encoding="utf-8")
        noop_index = source.index("plan.sync_status === 'up_to_date'")
        post_index = source.index("fetch('/api/sam/level1/send'")
        self.assertLess(noop_index, post_index)
        noop_section = source[noop_index:post_index]
        self.assertIn("Level 1 in SAM", noop_section)
        self.assertNotIn("method: 'POST'", noop_section)

    def test_sysml_output_remains_text_based(self) -> None:
        template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-output-tab="sysml"', template)
        self.assertIn('class="sysml-code-placeholder"', template)
        self.assertNotIn('id="sysmlBlockDiagram"', template)

    def test_web_state_exposes_explicit_level1_preview_contract(self) -> None:
        source = (ROOT / "web_app.py").read_text(encoding="utf-8")
        self.assertIn("build_sysml_level1_preview", source)
        self.assertIn('model_state["sysml_v2_level1"]', source)
        self.assertIn('model_state["sysml_v2"] = preview["text"]', source)

    def test_level1_backend_exposes_readonly_plan_and_confirmed_send(self) -> None:
        source = (ROOT / "web_app.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/sam/level1/plan")', source)
        self.assertIn("preview_level1_with_incremental_state", source)
        self.assertIn('@app.post("/api/sam/level1/send")', source)
        self.assertIn('body.get("confirm") is not True', source)
        self.assertIn("sync_level1_to_sam_verified", source)


if __name__ == "__main__":
    unittest.main()
