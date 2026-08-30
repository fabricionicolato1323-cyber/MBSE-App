from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session

from model_io import (
    ModelFileError,
    fallback_model_name_from_filename,
    model_name_from_payload,
    normalize_model_name,
    prepare_model_export,
    validate_model_payload,
)
from ui_guidance import configured_section
from web_ai import LocalAIServiceError, list_installed_models, load_web_ai_config
from web_model_session import ModelFileSessionRegistry
from web_ui_policy import should_track_temporary_input

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_ROOT = BASE_DIR / ".web_runtime"

app = Flask(__name__)
app.secret_key = os.getenv("MBSE_WEB_SECRET") or secrets.token_hex(32)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
registry = ModelFileSessionRegistry(BASE_DIR, RUNTIME_ROOT)


@app.after_request
def disable_development_asset_cache(response):
    """Always serve the current local UI while the prototype is under development."""
    if request.path == "/" or request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def current_session(*, create_if_missing: bool = True):
    session_id = session.get("mbse_session_id")
    current = registry.get(session_id) if session_id else None
    if current is None and create_if_missing:
        session_id, current = registry.create()
        session["mbse_session_id"] = session_id
    return session_id, current


def discover_local_ai_models() -> list[str]:
    config = load_web_ai_config()
    timeout = min(float(config.get("timeout_seconds", 5.0)), 5.0)
    return list_installed_models(
        base_url=str(config.get("base_url", "http://localhost:11434")),
        timeout_seconds=max(0.5, timeout),
    )


@app.get("/")
def index():
    current_session()
    return render_template("index.html")


@app.get("/api/ui-guidance/oa-help")
def api_oa_help():
    """Expose configurable, presentation-only Arcadia help to the web UI."""
    return jsonify(configured_section("oa_help"))


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


@app.post("/api/model/export")
def api_model_export():
    _, current = current_session(create_if_missing=False)
    if current is None:
        return jsonify({"ok": False, "error": "The modeling session is no longer active."}), 409

    payload = request.get_json(silent=True) or {}
    try:
        model_name = normalize_model_name(str(payload.get("model_name", "")))
        model = current.export_model(model_name)
    except ModelFileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409

    return jsonify({"ok": True, "model_name": model_name, "model": model})


@app.post("/api/model/load")
def api_model_load():
    session_id, current = current_session(create_if_missing=False)
    payload = request.get_json(silent=True) or {}
    file_name = str(payload.get("file_name", ""))

    try:
        normalized = validate_model_payload(payload.get("model"))
        proposed_name = (
            model_name_from_payload(normalized)
            or fallback_model_name_from_filename(file_name)
        )
        model_name = normalize_model_name(proposed_name)
        normalized = prepare_model_export(normalized, model_name)
    except ModelFileError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    try:
        new_session_id, _ = registry.load(session_id, normalized, model_name)
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409

    session["mbse_session_id"] = new_session_id
    return jsonify(
        {
            "ok": True,
            "session_id": new_session_id,
            "model_name": model_name,
            "counts": {
                "nodes": len(normalized.get("nodes", [])),
                "edges": len(normalized.get("edges", [])),
            },
        }
    )


@app.get("/api/ai/models")
def api_ai_models():
    _, current = current_session(create_if_missing=False)
    if current is None:
        return jsonify({"ok": False, "error": "The modeling session is no longer active."}), 409
    try:
        models = discover_local_ai_models()
    except LocalAIServiceError:
        return jsonify(
            {
                "ok": False,
                "available": False,
                "models": [],
                "error": "The local AI service is unavailable.",
            }
        ), 503
    return jsonify({"ok": True, "available": True, "models": models})


@app.post("/api/ai/activate")
def api_ai_activate():
    _, current = current_session(create_if_missing=False)
    if current is None:
        return jsonify({"ok": False, "error": "The modeling session is no longer active."}), 409

    payload = request.get_json(silent=True) or {}
    model = str(payload.get("model", "")).strip()
    if not model:
        return jsonify({"ok": False, "error": "Select a local model first."}), 400

    try:
        installed = discover_local_ai_models()
    except LocalAIServiceError:
        return jsonify({"ok": False, "error": "The local AI service is unavailable."}), 503
    if model not in installed:
        return jsonify({"ok": False, "error": "The selected model is not installed locally."}), 400

    request_id = current.request_ai("activate", model=model)
    return jsonify({"ok": True, "request_id": request_id}), 202


@app.post("/api/ai/disable")
def api_ai_disable():
    _, current = current_session(create_if_missing=False)
    if current is None:
        return jsonify({"ok": False, "error": "The modeling session is no longer active."}), 409
    request_id = current.request_ai("disable")
    return jsonify({"ok": True, "request_id": request_id}), 202


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
