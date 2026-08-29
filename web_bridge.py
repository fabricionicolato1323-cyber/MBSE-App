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

WAIT_INPUT = "> "
WAIT_CONTINUE = "Press Enter to return to the current question..."
CHOICE_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class ChatTurn:
    role: str
    content: str
    kind: str = "message"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


class TerminalProcessSession:
    """Bridge the existing terminal workflow to a browser-friendly session.

    The terminal application remains authoritative for sequencing, validation,
    confirmations, and model writes. This class only adapts stdin/stdout and
    exposes the live model snapshot written by web_worker.py.
    """

    def __init__(self, project_dir: Path, runtime_dir: Path) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.runtime_dir = Path(runtime_dir).resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.runtime_dir / "oa_model_web.json"
        self._lock = threading.RLock()
        self._stdout = ""
        self._published_stdout = ""
        self._waiting = False
        self._closed = False
        self._model_mtime_ns = 0
        self.pending_draft: dict[str, Any] | None = None
        self.turns: list[ChatTurn] = []

        command = [
            sys.executable,
            "-u",
            str(self.project_dir / "web_worker.py"),
            "--model-path",
            str(self.model_path),
        ]
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        self.process = subprocess.Popen(
            command,
            cwd=str(self.project_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,
            env=env,
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        while True:
            chunk = self.process.stdout.read(1)
            if chunk == "":
                break
            with self._lock:
                self._stdout += chunk
                if self._looks_ready_for_input(self._stdout):
                    self._waiting = True
        with self._lock:
            self._closed = True
            self._waiting = True

    @staticmethod
    def _looks_ready_for_input(text: str) -> bool:
        if text.endswith(WAIT_INPUT):
            return True
        if text.rstrip().endswith(WAIT_CONTINUE):
            return True
        return False

    @staticmethod
    def _clean_assistant_text(raw: str) -> str:
        text = raw.replace("\r", "")
        text = text.replace(WAIT_INPUT, "")
        text = text.replace(WAIT_CONTINUE, "")
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue
            if stripped and set(stripped) <= {"=", "-"}:
                continue
            if stripped == "GUIDED OPERATIONAL MODEL BUILDER":
                continue
            if stripped.startswith("Commands: /help"):
                continue
            lines.append(line.rstrip())

        cleaned = "\n".join(lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    @staticmethod
    def _current_prompt_text(raw: str) -> str:
        """Return only the newest terminal question block.

        The terminal intentionally keeps its full history. Browser actions must
        not therefore reuse numbered choices from an earlier question.
        """
        marker = "=" * 72
        index = raw.rfind(marker)
        return raw[index:] if index >= 0 else raw

    @staticmethod
    def _buttons_from_text(raw: str) -> list[dict[str, str]]:
        if raw.rstrip().endswith(WAIT_CONTINUE):
            return [{"label": "Continue", "value": ""}]

        prompt = TerminalProcessSession._current_prompt_text(raw)
        if "(yes/no)" in prompt.casefold():
            return [
                {"label": "Yes", "value": "yes"},
                {"label": "No", "value": "no"},
            ]

        choices = CHOICE_RE.findall(prompt)
        if choices:
            result: list[dict[str, str]] = []
            for number, label in choices[-12:]:
                result.append({"label": label.strip(), "value": number})
            return result
        return []

    def _publish_if_ready(self) -> None:
        with self._lock:
            if not self._waiting:
                return
            if self._stdout == self._published_stdout:
                return
            delta = self._stdout[len(self._published_stdout):]
            self._published_stdout = self._stdout
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

    def send(self, value: str, *, display_value: str | None = None) -> None:
        self._publish_if_ready()
        with self._lock:
            if self._closed:
                return
            if not self._waiting:
                raise RuntimeError("The model is still processing the previous input.")
            self._waiting = False

            shown = display_value if display_value is not None else value
            if shown:
                self.turns.append(ChatTurn(role="user", content=shown))
            if value and not value.lstrip().startswith("/"):
                self.pending_draft = {
                    "id": "pending-input",
                    "name": value.strip(),
                    "type": "Pending",
                    "status": "temporary",
                }

            assert self.process.stdin is not None
            self.process.stdin.write(value + "\n")
            self.process.stdin.flush()

    def command(self, command: str) -> None:
        labels = {
            "/help": "Help",
            "/show": "Show model",
            "/check": "Check model",
            "/why": "Why this question?",
            "/save": "Save",
            "/undo": "Undo",
            "/compare": "Compare with rules",
            "/done": "Finish",
        }
        self.send(command, display_value=labels.get(command, command))

    def model_snapshot(self) -> dict[str, Any]:
        self._refresh_draft_state()
        snapshot: dict[str, Any] = {"nodes": [], "edges": [], "counts": {"nodes": 0, "edges": 0}}
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
            raw_delta = self._stdout[len(self._published_stdout):]
            buttons = self._buttons_from_text(raw_delta if raw_delta else self._stdout)
            if self._waiting and not buttons:
                buttons = self._buttons_from_text(self._stdout)
            return {
                "turns": [turn.__dict__ for turn in self.turns],
                "waiting": self._waiting,
                "closed": self._closed,
                "buttons": buttons,
                "model": self.model_snapshot(),
            }

    def close(self) -> None:
        with self._lock:
            if self.process.poll() is None:
                self.process.terminate()
            self._closed = True


class SessionRegistry:
    def __init__(self, project_dir: Path, runtime_root: Path) -> None:
        self.project_dir = Path(project_dir)
        self.runtime_root = Path(runtime_root)
        self._sessions: dict[str, TerminalProcessSession] = {}
        self._lock = threading.Lock()

    def create(self) -> tuple[str, TerminalProcessSession]:
        with self._lock:
            session_id = uuid.uuid4().hex
            session = TerminalProcessSession(
                self.project_dir,
                self.runtime_root / session_id,
            )
            self._sessions[session_id] = session
            return session_id, session

    def get(self, session_id: str) -> TerminalProcessSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def reset(self, session_id: str) -> TerminalProcessSession:
        with self._lock:
            old = self._sessions.pop(session_id, None)
            if old is not None:
                old.close()
            session = TerminalProcessSession(
                self.project_dir,
                self.runtime_root / session_id,
            )
            self._sessions[session_id] = session
            return session
