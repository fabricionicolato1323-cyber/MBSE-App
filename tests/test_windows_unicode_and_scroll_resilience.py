from pathlib import Path


def test_windows_streams_use_safe_encoding_error_handling():
    source = Path('sitecustomize.py').read_text(encoding='utf-8')
    assert 'backslashreplace' in source
    assert 'reconfigure' in source


def test_active_question_is_not_forced_back_into_view_on_every_poll():
    source = Path('static/question_notice_separation.js').read_text(encoding='utf-8')
    assert 'revisionLastAutoRevealTurnId' in source
    assert 'turnId === revisionLastAutoRevealTurnId' in source


def test_raw_traceback_is_kept_out_of_chat_bubble():
    source = Path('static/question_notice_separation.js').read_text(encoding='utf-8')
    assert 'Traceback \\(most recent call last\\):' in source
    assert 'Technical details were saved to worker.log.' in source
