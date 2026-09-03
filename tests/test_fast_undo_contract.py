from pathlib import Path

from web_bridge import ChatTurn
from web_model_session import ModelFileSession


ROOT = Path(__file__).resolve().parents[1]


def test_fast_undo_preserves_question_before_last_answer():
    turns = [
        ChatTurn(role="assistant", content="What is the main goal?", id="q1"),
        ChatTurn(role="user", content="Ensure safe passage", id="a1"),
        ChatTurn(role="assistant", content="Is there another goal?", id="q2"),
        ChatTurn(role="user", content="No", id="a2"),
        ChatTurn(role="assistant", content="Who or what is involved?", id="q3"),
    ]

    preserved = ModelFileSession._turns_before_last_answer(turns)

    assert [turn.id for turn in preserved] == ["q1", "a1", "q2"]
    assert preserved[-1].content == "Is there another goal?"


def test_fast_undo_with_no_user_turn_keeps_existing_chat():
    turns = [ChatTurn(role="assistant", content="What is the main goal?", id="q1")]
    preserved = ModelFileSession._turns_before_last_answer(turns)
    assert [turn.id for turn in preserved] == ["q1"]


def test_incremental_chat_renderer_does_not_clear_entire_chat():
    source = (ROOT / "static" / "question_notice_separation.js").read_text(
        encoding="utf-8"
    )

    incremental_start = source.index(
        "renderRevisionTurns = function separatedRevisionTurns"
    )
    incremental_body = source[incremental_start:]

    assert "revisionDesiredRows" in source
    assert "commonPrefix" in incremental_body
    assert "removeChild(chatRoot.lastElementChild)" in incremental_body
    assert "chatRoot.innerHTML = ''" not in incremental_body


def test_fast_undo_replay_restores_ai_after_history_replay():
    source = (ROOT / "web_model_session.py").read_text(encoding="utf-8")
    replay_index = source.index("for value, display_value in prior_history:")
    restore_ai_index = source.index("if active_ai_model:", replay_index)
    assert restore_ai_index > replay_index
    assert "silent and runs with AI disabled" in source
