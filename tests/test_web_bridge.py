from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web_bridge import SessionRegistry, TerminalProcessSession
from web_protocol import encode_interaction


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

    @staticmethod
    def _snapshot_session(active_prompt: str):
        session = TerminalProcessSession.__new__(TerminalProcessSession)
        session._active_prompt_raw = active_prompt
        session._waiting = True
        session._stdout = active_prompt
        session._published_stdout = active_prompt
        return session

    def test_visible_yes_no_overrides_incorrect_free_text_marker(self):
        raw = (
            encode_interaction({"mode": "free_text", "choices": []})
            + "\nIs there another important goal? (yes/no)\n"
            + "  Expected answer: yes / no\n> "
        )
        interaction = self._snapshot_session(raw).interaction_snapshot()
        self.assertEqual(interaction["mode"], "yes_no")
        self.assertEqual(
            interaction["choices"],
            [
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ],
        )

    def test_visible_numbered_options_override_incorrect_free_text_marker(self):
        raw = (
            encode_interaction({"mode": "free_text", "choices": []})
            + "\nWhich action receives it?\n"
            + "  1. First action\n"
            + "  2. Second action\n> "
        )
        interaction = self._snapshot_session(raw).interaction_snapshot()
        self.assertEqual(interaction["mode"], "choice")
        self.assertEqual(
            interaction["choices"],
            [
                {"label": "First action", "value": "1"},
                {"label": "Second action", "value": "2"},
            ],
        )

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
