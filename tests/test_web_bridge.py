from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web_bridge import SessionRegistry, TerminalProcessSession


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

    def test_clean_text_hides_technical_startup_details(self):
        raw = (
            "Loading Arcadia knowledge graph...\n"
            "Elapsed processing time: 0.03 s\n"
            "Connecting to Ollama...\n"
            "Elapsed processing time: 0.05 s\n"
            "Ollama is unavailable, so the app will continue with deterministic rules. "
            "Details: More than one Ollama model is installed. "
            "Available models: model-a, model-b.\n"
            "What is the main goal?\n> "
        )
        clean = TerminalProcessSession._clean_assistant_text(raw)
        self.assertIn(
            "AI assistance is unavailable. Deterministic validation is active.",
            clean,
        )
        self.assertIn("What is the main goal?", clean)
        self.assertNotIn("Ollama", clean)
        self.assertNotIn("Arcadia", clean)
        self.assertNotIn("model-a", clean)

    def test_clean_text_neutralizes_method_names(self):
        raw = (
            "ARCADIA KNOWLEDGE GRAPH COMPARISON\n"
            "Compare the current model with Arcadia rules.\n"
            "Ask an Arcadia method question.\n"
        )
        clean = TerminalProcessSession._clean_assistant_text(raw)
        self.assertIn("MODELING RULE COMPARISON", clean)
        self.assertIn("modeling rules", clean)
        self.assertIn("modeling method", clean)
        self.assertNotIn("Arcadia", clean)


class RegistryResetTests(unittest.TestCase):
    def test_reset_replaces_session_identity(self):
        created = []

        class FakeSession:
            def __init__(self, project_dir, runtime_dir):
                self.project_dir = Path(project_dir)
                self.runtime_dir = Path(runtime_dir)
                self.closed = False
                created.append(self)

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as tmp, patch(
            "web_bridge.TerminalProcessSession",
            FakeSession,
        ):
            registry = SessionRegistry(Path(tmp), Path(tmp) / "runtime")
            old_id, old_session = registry.create()
            new_id, new_session = registry.reset(old_id)

            self.assertNotEqual(old_id, new_id)
            self.assertTrue(old_session.closed)
            self.assertIsNone(registry.get(old_id))
            self.assertIs(registry.get(new_id), new_session)


if __name__ == "__main__":
    unittest.main()
