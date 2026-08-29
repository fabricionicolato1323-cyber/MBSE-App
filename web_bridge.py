from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from web_protocol import (
    decode_latest_interaction,
    is_interaction_protocol_line,
    normalize_interaction,
)

WAIT_INPUT = "> "
WAIT_CONTINUE = "Press Enter to return to the current question..."
CHOICE_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class ChatTurn:
    role: str
    content: str
    kind: str = "message"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


class TerminalProcessSession:
    """Bridge the terminal workflow to a browser-friendly, rewindable session."""

    def __init__(self, project_dir: Path, runtime_dir: Path) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.runtime_dir = Path(runtime_dir).resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.runtime_dir / "oa_model_web.json"
        self.diagnostic_path = self.runtime_dir / "worker.log"
        self.ai_command_path = self.runtime_dir / "ai_command.json"
        self.ai_status_path = self.runtime_dir / "ai_status.json"
        self._lock = threading.RLock()
        self._stdout = ""
        self._published_stdout = ""
        self._active_prompt_raw = ""
        self._waiting = False
        self._closed = False
        self._model_mtime_ns = 0
        self.pending_draft: dict[str, Any] | None = None
        self.turns: list[ChatTurn] = []
        self.input_history: list[tuple[str, str | None]] = []
        self._restoring = False
        self.process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._launch_worker()

    def _launch_worker(self) -> None:
        command = [
            sys.executable,
            "-u",
            str(self.project_dir / "web_worker.py"),
            "--model-path",
            str(self.model_path),
        ]
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        process = subprocess.Popen(
            command,
            cwd=str(self.project_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=0,
            env=env,
        )
        with self._lock:
            self.process = process
            self._closed = False
        self._reader = threading.Thread(
            target=self._read_stdout,
            args=(process,),
            daemon=True,
        )
        self._reader.start()

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(1)
            if chunk == "":
                break
            with self._lock:
                if process is not self.process:
                    continue
                self._stdout += chunk
                if self._looks_ready_for_input(self._stdout):
                    self._waiting = True
        with self._lock:
            if process is self.process:
                self._closed = True
                self._waiting = True

    @staticmethod
    def _looks_ready_for_input(text: str) -> bool:
        if text.endswith(WAIT_INPUT):
            return True
        if text.rstrip().endswith(WAIT_CONTINUE):
            return True
        return False

    def _append_diagnostic(self, raw: str) -> None:
        if not raw:
            return
        try:
            with self.diagnostic_path.open("a", encoding="utf-8") as handle:
                handle.write(raw)
        except OSError:
            pass

    @staticmethod
    def _neutralize_web_line(line: str) -> str | None:
        stripped = line.strip()
        if not stripped:
            return ""

        if is_interaction_protocol_line(line):
            return None

        hidden_prefixes = (
            "Loading Arcadia knowledge graph",
            "Elapsed processing time:",
            "Connecting to Ollama",
            "Ollama connected. Selected model:",
            "Ollama responses:",
        )
        if stripped.startswith(hidden_prefixes):
            return None

        if stripped.startswith("Ollama is unavailable"):
            return None

        replacements = (
            ("ARCADIA KNOWLEDGE GRAPH COMPARISON", "MODELING RULE COMPARISON"),
            ("ARCADIA KNOWLEDGE ANSWER", "MODELING KNOWLEDGE ANSWER"),
            ("Arcadia knowledge graph", "modeling knowledge"),
            ("Arcadia rules", "modeling rules"),
            ("Arcadia method", "modeling method"),
            ("RDF/SHACL Arcadia rules", "configured modeling rules"),
            ("Ollama", "AI assistance"),
        )
        neutral = line.rstrip()
        for old, new in replacements:
            neutral = neutral.replace(old, new)
        return neutral

    @staticmethod
    def _clean_assistant_text(raw: str) -> str:
        text = raw.replace("\r", "")
        text = text.replace(WAIT_INPUT, "")
        text = text.replace(WAIT_CONTINUE, "")
        lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and set(stripped) <= {"=", "-"}:
                continue
            if stripped == "GUIDED OPERATIONAL MODEL BUILDER":
                continue
            if stripped.startswith("Commands: /help"):
                continue

            neutral = TerminalProcessSession._neutralize_web_line(line)
            if neutral is None:
                continue
            lines.append(neutral)

        cleaned = "\n".join(lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    @staticmethod
    def _current_prompt_text(raw: str) -> str:
        marker = "=" * 72
        index = raw.rfind(marker)
        return raw[index:] if index >= 0 else raw

    @staticmethod
    def _fallback_interaction_from_text(raw: str) -> dict[str, Any]:
        if raw.rstrip().endswith(WAIT_CONTINUE):
            return normalize_interaction({"mode": "continue"})

        prompt = TerminalProcessSession._current_prompt_text(raw)
        if "(yes/no)" in prompt.casefold():
            return normalize_interaction({"mode": "yes_no"})

        choices = CHOICE_RE.findall(prompt)
        if choices:
            return normalize_interaction(
                {
                    "mode": "choice",
                    "choices": [
                        {"label": label.strip(), "value": number}
                        for number, label in choices[-20:]
                    ],
                }
            )

        return normalize_interaction({"mode": "free_text"})

    @staticmethod
    def _buttons_from_text(raw: str) -> list[dict[str, str]]:
        return TerminalProcessSession._fallback_interaction_from_text(raw)["choices"]

    def interaction_snapshot(self) -> dict[str, Any]:
        raw = self._active_prompt_raw
        if not raw and self._waiting:
            unpublished = self._stdout[len(self._published_stdout):]
            raw = unpublished or self._current_prompt_text(self._stdout)

        explicit = decode_latest_interaction(raw)
        fallback = self._fallback_interaction_from_text(raw)
        if explicit is None:
            return fallback

        if fallback["mode"] in {"yes_no", "choice", "continue"}:
            if explicit["mode"] == "free_text":
                return fallback
            if explicit["mode"] == "choice" and not explicit["choices"]:
                return fallback
        return explicit

    def _publish_if_ready(self) -> None:
        with self._lock:
            if not self._waiting:
                return
            if self._stdout == self._published_stdout:
                return
            delta = self._stdout[len(self._published_stdout):]
            self._published_stdout = self._stdout
            self._active_prompt_raw = delta
            self._append_diagnostic(delta)
            clean = self._clean_assistant_text(delta)
            if clean:
                self.turns.append(ChatTurn(role="assistant", content=clean))
            self._refresh_draft_state(clean)

    def _refresh_draft_state(self, assistant_text: str = "") -> None:
        changed = False
        if self.model_path.exists():
            stat = self.model_path.stat()
            if stat.st_mtime_ns > self._model_mtime_ns:
                self._model_mtime_ns = stat.st_mtime_ns
                changed = True
        rejection = any(
            marker in assistant_text.casefold()
            for marker in (
                "nothing was added",
                "candidate rejected",
                "was not added",
                "interpretation rejected",
            )
        )
        if changed or rejection:
            self.pending_draft = None

    def send(
        self,
        value: str,
        *,
        display_value: str | None = None,
        record_history: bool = True,
    ) -> None:
        self._publish_if_ready()
        with self._lock:
            process = self.process
            if process is None or self._closed:
                raise RuntimeError("The modeling session is no longer active.")
            if not self._waiting:
                raise RuntimeError("The model is still processing the previous input.")
            self._waiting = False
            self._active_prompt_raw = ""

            shown = display_value if display_value is not None else value
            if shown:
                self.turns.append(ChatTurn(role="user", content=shown))
            if record_history and value and not value.lstrip().startswith("/"):
                self.input_history.append((value, display_value))
            if value and not value.lstrip().startswith("/"):
                self.pending_draft = {
                    "id": "pending-input",
                    "name": value.strip(),
                    "type": "Pending",
                    "status": "temporary",
                }

            assert process.stdin is not None
            process.stdin.write(value + "\n")
            process.stdin.flush()

    def _terminate_worker(self) -> None:
        with self._lock:
            process = self.process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)

    def _wait_until_waiting(self, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                closed = self._closed
                waiting = self._waiting
            if closed:
                self._publish_if_ready()
                raise RuntimeError("The modeling worker stopped while restoring the previous step.")
            if waiting:
                self._publish_if_ready()
                return
            time.sleep(0.02)
        raise RuntimeError("Timed out while restoring the previous modeling step.")

    def _wait_for_ai_model(self, model: str, timeout: float = 15.0) -> None:
        self.request_ai("activate", model=model)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.ai_snapshot()
            if status.get("status") == "active" and status.get("model") == model:
                return
            if status.get("status") == "error":
                raise RuntimeError("AI assistance could not be restored after Undo.")
            time.sleep(0.05)
        raise RuntimeError("Timed out while restoring AI assistance after Undo.")

    def _reset_runtime_for_replay(self) -> None:
        for path in (self.model_path, self.ai_command_path, self.ai_status_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        with self._lock:
            self._stdout = ""
            self._published_stdout = ""
            self._active_prompt_raw = ""
            self._waiting = False
            self._closed = False
            self._model_mtime_ns = 0
            self.pending_draft = None
            self.turns = []
            self.process = None

    def undo_last_decision(self) -> None:
        """Undo one user decision by rebuilding the deterministic guided session.

        Replaying prior answers rewinds both NetworkX mutations and the Python
        call stack, so one Undo corresponds to one user answer rather than one
        low-level graph checkpoint.
        """
        self._publish_if_ready()
        with self._lock:
            if not self.input_history:
                raise RuntimeError("There is no previous user decision to undo.")
            prior_history = list(self.input_history[:-1])
        ai_state = self.ai_snapshot()
        active_ai_model = (
            ai_state.get("model")
            if ai_state.get("status") == "active"
            else None
        )

        self._append_diagnostic("\n\n--- WEB UNDO: rebuilding previous user step ---\n")
        with self._lock:
            self._restoring = True
        try:
            self._terminate_worker()
            self._reset_runtime_for_replay()
            with self._lock:
                self.input_history = prior_history
                self._restoring = True
            self._launch_worker()
            self._wait_until_waiting()

            if active_ai_model:
                self._wait_for_ai_model(str(active_ai_model))

            for value, display_value in prior_history:
                self._wait_until_waiting()
                self.send(
                    value,
                    display_value=display_value,
                    record_history=False,
                )
                self._wait_until_waiting()

            self._publish_if_ready()
        finally:
            with self._lock:
                self._restoring = False

    def command(self, command: str) -> None:
        if command == "/undo":
            self.undo_last_decision()
            return

        labels = {
            "/help": "Help",
            "/show": "Show model",
            "/check": "Check model",
            "/why": "Why this question?",
            "/save": "Save",
            "/compare": "Compare with rules",
            "/done": "Finish",
        }
        self.send(command, display_value=labels.get(command, command))

    def request_ai(self, action: str, *, model: str | None = None) -> str:
        request_id = uuid.uuid4().hex
        payload: dict[str, Any] = {
            "request_id": request_id,
            "action": action,
        }
        if model:
            payload["model"] = model
        _write_json_atomic(self.ai_command_path, payload)
        return request_id

    def ai_snapshot(self) -> dict[str, Any]:
        default = {
            "status": "off",
            "model": None,
            "message": "AI assistance is off.",
        }
        try:
            payload = json.loads(self.ai_status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default
        if not isinstance(payload, dict):
            return default
        status = str(payload.get("status", "off")).strip().casefold()
        if status not in {"off", "activating", "active", "error"}:
            status = "off"
        model = str(payload.get("model") or "").strip() or None
        message = str(payload.get("message") or "").strip()
        return {"status": status, "model": model, "message": message}

    def model_snapshot(self) -> dict[str, Any]:
        self._refresh_draft_state()
        snapshot: dict[str, Any] = {
            "nodes": [],
            "edges": [],
            "counts": {"nodes": 0, "edges": 0},
        }
        if self.model_path.exists():
            try:
                data = json.loads(self.model_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            nodes = []
            for item in data.get("nodes", []):
                node = dict(item)
                node.setdefault("status", "confirmed")
                nodes.append(node)
            edges = []
            for item in data.get("edges", []):
                edge = dict(item)
                edge.setdefault("status", "confirmed")
                edges.append(edge)
            snapshot = {
                "nodes": nodes,
                "edges": edges,
                "counts": {"nodes": len(nodes), "edges": len(edges)},
            }

        drafts = [self.pending_draft] if self.pending_draft else []
        snapshot["drafts"] = drafts
        return snapshot

    def state(self) -> dict[str, Any]:
        self._publish_if_ready()
        with self._lock:
            interaction = self.interaction_snapshot()
            effective_waiting = self._waiting and not self._restoring
            buttons = interaction["choices"] if effective_waiting else []
            return {
                "turns": [turn.__dict__ for turn in self.turns],
                "waiting": effective_waiting,
                "restoring": self._restoring,
                "closed": self._closed,
                "buttons": buttons,
                "interaction": interaction,
                "model": self.model_snapshot(),
                "ai": self.ai_snapshot(),
                "can_undo": bool(self.input_history),
            }

    def close(self) -> None:
        self._terminate_worker()
        with self._lock:
            self._closed = True


class SessionRegistry:
    def __init__(self, project_dir: Path, runtime_root: Path) -> None:
        self.project_dir = Path(project_dir)
        self.runtime_root = Path(runtime_root)
        self._sessions: dict[str, TerminalProcessSession] = {}
        self._lock = threading.Lock()

    def _create_unlocked(self) -> tuple[str, TerminalProcessSession]:
        session_id = uuid.uuid4().hex
        session = TerminalProcessSession(
            self.project_dir,
            self.runtime_root / session_id,
        )
        self._sessions[session_id] = session
        return session_id, session

    def create(self) -> tuple[str, TerminalProcessSession]:
        with self._lock:
            return self._create_unlocked()

    def get(self, session_id: str | None) -> TerminalProcessSession | None:
        if not session_id:
            return None
        with self._lock:
            return self._sessions.get(session_id)

    def reset(self, session_id: str) -> tuple[str, TerminalProcessSession]:
        with self._lock:
            old = self._sessions.pop(session_id, None)
            if old is not None:
                old.close()
            return self._create_unlocked()
