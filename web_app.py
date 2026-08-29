from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request, session

from web_bridge import SessionRegistry

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_ROOT = BASE_DIR / ".web_runtime"

app = Flask(__name__)
app.secret_key = "local-development-session-key"
registry = SessionRegistry(BASE_DIR, RUNTIME_ROOT)


def current_session():
    session_id = session.get("mbse_session_id")
    current = registry.get(session_id) if session_id else None
    if current is None:
        session_id, current = registry.create()
        session["mbse_session_id"] = session_id
    return session_id, current


@app.get("/")
def index():
    current_session()
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    _, current = current_session()
    return jsonify(current.state())


@app.post("/api/input")
def api_input():
    _, current = current_session()
    payload = request.get_json(silent=True) or {}
    value = str(payload.get("value", ""))
    display_value = payload.get("display_value")
    try:
        current.send(value, display_value=display_value)
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True})


@app.post("/api/command")
def api_command():
    _, current = current_session()
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
    session_id, _ = current_session()
    registry.reset(session_id)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
