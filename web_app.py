from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session

from web_bridge import SessionRegistry
from web_ui_policy import should_track_temporary_input

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_ROOT = BASE_DIR / ".web_runtime"

app = Flask(__name__)
app.secret_key = os.getenv("MBSE_WEB_SECRET") or secrets.token_hex(32)
registry = SessionRegistry(BASE_DIR, RUNTIME_ROOT)


def current_session(*, create_if_missing: bool = True):
    session_id = session.get("mbse_session_id")
    current = registry.get(session_id) if session_id else None
    if current is None and create_if_missing:
        session_id, current = registry.create()
        session["mbse_session_id"] = session_id
    return session_id, current


@app.get("/")
def index():
    current_session()
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    session_id, current = current_session(create_if_missing=False)
    if current is None:
        return jsonify({"ok": False, "stale_session": True, "session_id": session_id}), 409
    state = current.state()
    state["session_id"] = session_id
    return jsonify(state)


@app.post("/api/input")
def api_input():
    _, current = current_session(create_if_missing=False)
    if current is None:
        return jsonify({"ok": False, "error": "The modeling session is no longer active."}), 409

    payload = request.get_json(silent=True) or {}
    value = str(payload.get("value", ""))
    display_value = payload.get("display_value")
    interaction = current.interaction_snapshot()
    track_temporary = should_track_temporary_input(value, interaction)

    try:
        # Keep control answers atomic with draft suppression. TerminalProcessSession
        # uses an RLock, so send() can safely re-enter it while state polling waits.
        with current._lock:  # noqa: SLF001 - local web adapter boundary
            current.send(value, display_value=display_value)
            if not track_temporary:
                current.pending_draft = None
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True})


@app.post("/api/command")
def api_command():
    _, current = current_session(create_if_missing=False)
    if current is None:
        return jsonify({"ok": False, "error": "The modeling session is no longer active."}), 409

    payload = request.get_json(silent=True) or {}
    command = str(payload.get("command", "")).strip()
    allowed = {
        "/help",
        "/show",
        "/check",
        "/why",
        "/save",
        "/undo",
        "/compare",
        "/done",
    }
    if command not in allowed:
        return jsonify({"ok": False, "error": "Unsupported command."}), 400
    try:
        current.command(command)
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True})


@app.post("/api/reset")
def api_reset():
    session_id, current = current_session(create_if_missing=False)
    if session_id and current is not None:
        new_session_id, _ = registry.reset(session_id)
    else:
        new_session_id, _ = registry.create()
    session["mbse_session_id"] = new_session_id
    return jsonify({"ok": True, "session_id": new_session_id})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
