from pathlib import Path
import json
import tempfile
import unittest

from web_bridge import TerminalProcessSession


class BridgeParsingTests(unittest.TestCase):
    def test_yes_no_buttons(self):
        buttons = TerminalProcessSession._buttons_from_text("Continue? (yes/no)\n> ")
        self.assertEqual([item["value"] for item in buttons], ["yes", "no"])

    def test_numbered_buttons(self):
        raw = "Choose one:\n  1. First option\n  2. Second option\n\n> "
        buttons = TerminalProcessSession._buttons_from_text(raw)
        self.assertEqual(buttons[0], {"label": "First option", "value": "1"})
        self.assertEqual(buttons[1], {"label": "Second option", "value": "2"})

    def test_continue_button(self):
        raw = "MODEL SO FAR\nPress Enter to return to the current question..."
        self.assertEqual(
            TerminalProcessSession._buttons_from_text(raw),
            [{"label": "Continue", "value": ""}],
        )


    def test_old_numbered_choices_do_not_leak_into_new_yes_no_prompt(self):
        raw = (
            "========================================================================\n"
            "Choose one:\n"
            "  1. First option\n"
            "  2. Second option\n\n> 1\n"
            "========================================================================\n"
            "Continue? (yes/no)\n> "
        )
        self.assertEqual(
            TerminalProcessSession._buttons_from_text(raw),
            [
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

    def test_old_numbered_choices_do_not_leak_into_free_text_prompt(self):
        raw = (
            "========================================================================\n"
            "Choose one:\n"
            "  1. First option\n"
            "  2. Second option\n\n> 1\n"
            "========================================================================\n"
            "What is the main goal?\n> "
        )
        self.assertEqual(TerminalProcessSession._buttons_from_text(raw), [])

    def test_clean_text_removes_terminal_chrome(self):
        raw = (
            "========================================================================\n"
            "GUIDED OPERATIONAL MODEL BUILDER\n"
            "Commands: /help  /show\n"
            "------------------------------------------------------------------------\n"
            "What is the main goal?\n> "
        )
        clean = TerminalProcessSession._clean_assistant_text(raw)
        self.assertEqual(clean, "What is the main goal?")


if __name__ == "__main__":
    unittest.main()
