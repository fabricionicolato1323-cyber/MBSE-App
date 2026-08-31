from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OperationalActivityPresentationTests(unittest.TestCase):
    def test_pseudo_code_separates_activity_list_from_assignments(self) -> None:
        source = (ROOT / "static" / "revision_model.js").read_text(encoding="utf-8")
        self.assertIn("addSection('Operational Activities')", source)
        self.assertIn("heading.textContent = 'Activity assignments'", source)
        self.assertIn("edge.type === 'PERFORMS'", source)
        self.assertIn("revisionFriendlyType(participant.type)", source)

    def test_participant_section_no_longer_embeds_performed_activities(self) -> None:
        source = (ROOT / "static" / "revision_model.js").read_text(encoding="utf-8")
        participants_start = source.index("const participants =")
        activities_start = source.index("const activities =")
        participant_section = source[participants_start:activities_start]
        self.assertNotIn("edge.type === 'PERFORMS'", participant_section)
        self.assertNotIn("OperationalActivity", participant_section)


if __name__ == "__main__":
    unittest.main()
