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
        self.assertIn("SAM not written", source)
        self.assertIn("Export Level 1 .sysml", source)

    def test_level1b_requires_plan_and_explicit_confirmation_before_send(self) -> None:
        source = (ROOT / "static" / "sysml_v2_render.js").read_text(encoding="utf-8")
        self.assertIn("Send Level 1 to SAM", source)
        self.assertIn("/api/sam/level1/plan", source)
        self.assertIn("window.confirm", source)
        self.assertIn("/api/sam/level1/send", source)
        self.assertIn("snapshot_digest", source)
        self.assertIn("confirm: true", source)

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

    def test_level1b_backend_exposes_plan_and_transactional_send_endpoints(self) -> None:
        source = (ROOT / "web_app.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/sam/level1/plan")', source)
        self.assertIn('@app.post("/api/sam/level1/send")', source)
        self.assertIn('body.get("confirm") is not True', source)
        self.assertIn("sync_level1_to_sam", source)


if __name__ == "__main__":
    unittest.main()
