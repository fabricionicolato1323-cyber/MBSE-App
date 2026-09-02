from web_protocol import encode_interaction
from web_ui_policy import interaction_from_prompt_delta, should_track_temporary_input


def test_current_prompt_marker_wins():
    old = encode_interaction({"mode": "free_text"})
    current = encode_interaction({"mode": "yes_no"})
    assert interaction_from_prompt_delta(current + "\nQuestion?\n", {"mode": "free_text"})["mode"] == "yes_no"
    assert interaction_from_prompt_delta(old + "\nOld question\n", {"mode": "choice"})["mode"] == "free_text"


def test_control_answers_are_not_temporary_model_facts():
    assert not should_track_temporary_input("no", {"mode": "yes_no"})
    assert not should_track_temporary_input("yes", {"mode": "yes_no"})
    assert not should_track_temporary_input("2", {"mode": "choice"})
    assert not should_track_temporary_input("", {"mode": "continue"})


def test_free_text_can_be_temporary():
    assert should_track_temporary_input("Request entry", {"mode": "free_text"})
    assert not should_track_temporary_input("/show", {"mode": "free_text"})
