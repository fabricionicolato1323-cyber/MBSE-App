from __future__ import annotations

import unittest
from unittest.mock import patch

from sysml_level1 import build_sysml_level1_preview


class SysMLLevel1PreviewTests(unittest.TestCase):
    def test_preview_reports_complete_confirmed_model_scope_without_sam_write(self) -> None:
        model = {
            "nodes": [
                {"id": "entity-1", "type": "OperationalEntity", "name": "Entity"},
                {"id": "activity-1", "type": "OperationalActivity", "name": "Activity"},
            ],
            "edges": [
                {
                    "source": "entity-1",
                    "target": "activity-1",
                    "type": "PERFORMS",
                }
            ],
        }
        scenarios = [
            {"id": "scenario-1", "name": "Scenario", "valid": True, "steps": []},
            {"id": "scenario-invalid", "name": "Invalid", "valid": False, "steps": []},
        ]
        drafts = [{"id": "draft-1", "type": "Pending", "name": "Temporary"}]

        with patch("sysml_level1.generate_sysml_v2", return_value="package OA_Test {}\n") as generator:
            preview = build_sysml_level1_preview(
                model,
                scenarios=scenarios,
                drafts=drafts,
            )

        generator.assert_called_once()
        self.assertEqual(preview["level"], 1)
        self.assertEqual(preview["phase"], "A")
        self.assertEqual(preview["kind"], "model")
        self.assertEqual(preview["scope"], "complete_model")
        self.assertEqual(preview["status"], "ready")
        self.assertEqual(preview["text"], "package OA_Test {}\n")
        self.assertEqual(preview["counts"]["elements"], 2)
        self.assertEqual(preview["counts"]["relationships"], 1)
        self.assertEqual(preview["counts"]["scenarios"], 1)
        self.assertEqual(preview["counts"]["temporary_items"], 1)
        self.assertFalse(preview["sam_write_performed"])

    def test_empty_model_still_produces_a_local_preview_contract(self) -> None:
        with patch("sysml_level1.generate_sysml_v2", return_value="package OA_Empty {}\n"):
            preview = build_sysml_level1_preview({})

        self.assertEqual(preview["status"], "empty")
        self.assertEqual(preview["counts"]["elements"], 0)
        self.assertEqual(preview["counts"]["relationships"], 0)
        self.assertEqual(preview["counts"]["scenarios"], 0)
        self.assertFalse(preview["sam_write_performed"])


if __name__ == "__main__":
    unittest.main()
