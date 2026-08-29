from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_web_bridge_uses_explicit_utf8_worker_pipes():
    source = Path("web_bridge.py").read_text(encoding="utf-8")
    assert 'env["PYTHONUTF8"] = "1"' in source
    assert 'env["PYTHONIOENCODING"] = "utf-8"' in source
    assert 'encoding="utf-8"' in source
    assert 'errors="replace"' in source


def test_worker_overrides_legacy_code_page_for_numeric_operator_protocol():
    code = r'''
import web_worker
from web_protocol import encode_interaction

web_worker._configure_web_streams()
print(encode_interaction({
    "mode": "choice",
    "choices": [
        {"label": "At least (≥)", "value": "2"},
        {"label": "At most (≤)", "value": "4"},
    ],
}))
'''
    env = os.environ.copy()
    # Reproduce the kind of legacy Windows console encoding that cannot encode
    # ≥/≤, then verify web_worker explicitly switches the protocol to UTF-8.
    env["PYTHONIOENCODING"] = "cp1252"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path.cwd(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    output = result.stdout.decode("utf-8")
    assert "At least (≥)" in output
    assert "At most (≤)" in output


def test_active_question_is_not_forced_back_into_view_on_every_poll():
    source = Path("static/question_notice_separation.js").read_text(encoding="utf-8")
    assert "revisionLastAutoRevealTurnId" in source
    assert "turnId === revisionLastAutoRevealTurnId" in source


def test_raw_traceback_is_kept_out_of_chat_bubble():
    source = Path("static/question_notice_separation.js").read_text(encoding="utf-8")
    assert "Traceback \\(most recent call last\\):" in source
    assert "Technical details were saved to worker.log." in source
