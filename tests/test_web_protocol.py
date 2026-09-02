from web_bridge import TerminalProcessSession
from web_protocol import (
    decode_latest_interaction,
    encode_interaction,
    normalize_interaction,
)


def test_yes_no_protocol_round_trip():
    encoded = encode_interaction({"mode": "yes_no"})
    decoded = decode_latest_interaction(encoded)
    assert decoded == {
        "mode": "yes_no",
        "choices": [
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"},
        ],
    }


def test_latest_interaction_wins():
    raw = "\n".join(
        [
            encode_interaction({"mode": "free_text"}),
            "What is the main goal?",
            encode_interaction({"mode": "yes_no"}),
            "Is there another important goal? (yes/no)",
        ]
    )
    assert decode_latest_interaction(raw)["mode"] == "yes_no"


def test_choice_values_are_preserved():
    payload = normalize_interaction(
        {
            "mode": "choice",
            "choices": [
                {"label": "First", "value": "1"},
                {"label": "Second", "value": "2"},
            ],
        }
    )
    assert payload["choices"][1] == {"label": "Second", "value": "2"}


def test_protocol_marker_is_not_shown_in_chat():
    raw = (
        encode_interaction({"mode": "yes_no"})
        + "\nIs there another important goal? (yes/no)\n> "
    )
    clean = TerminalProcessSession._clean_assistant_text(raw)
    assert "__MBSE_WEB_INTERACTION__" not in clean
    assert "Is there another important goal?" in clean


def test_legacy_text_parser_remains_a_fallback():
    buttons = TerminalProcessSession._buttons_from_text(
        "Continue? (yes/no)\n> "
    )
    assert [item["value"] for item in buttons] == ["yes", "no"]
