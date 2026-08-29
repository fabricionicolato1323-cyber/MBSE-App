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
        # The browser/worker protocol contains Unicode labels such as ≥ and ≤.
        # Do not inherit the Windows console code page for either end of the
        # subprocess pipe; make the transport deterministic and lossless.
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
        if changed:
            self.pending_draft = self._load_model_snapshot()

    def _load_model_snapshot(self) -> dict[str, Any] | None:
        if not self.model_path.exists():
            return None
        try:
            return json.loads(self.model_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_input(self, value: str) -> bool:
        process = self.process
        if process is None or process.stdin is None or process.poll() is not None:
            return False
        try:
            process.stdin.write(value + "\n")
            process.stdin.flush()
            return True
        except (BrokenPipeError, OSError, ValueError):
            return False

    def submit(self, value: str, *, display_value: str | None = None) -> None:
        with self._lock:
            self._publish_if_ready()
            if self._closed:
                raise RuntimeError("The local modeling worker is not running.")
            if not self._waiting:
                raise RuntimeError("The local modeling worker is still processing.")

            shown = display_value if display_value is not None else value
            self.turns.append(ChatTurn(role="user", content=shown))
            self.input_history.append((value, display_value))
            self._waiting = False
            self._active_prompt_raw = ""
            if not self._write_input(value):
                self._closed = True
                self._waiting = True
                raise RuntimeError("The local modeling worker stopped unexpectedly.")

    def snapshot(self) -> dict[str, Any]:
        self._publish_if_ready()
        with self._lock:
            process = self.process
            closed = self._closed or process is None or process.poll() is not None
            if closed:
                self._closed = True
                self._waiting = True
            return {
                "turns": [turn.__dict__.copy() for turn in self.turns],
                "waiting": self._waiting,
                "closed": self._closed,
                "interaction": self.interaction_snapshot(),
                "model": self._load_model_snapshot(),
                "pending_draft": self.pending_draft,
            }

    def close(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        self._closed = True

    def restart(self) -> None:
        with self._lock:
            old_process = self.process
            self.process = None
            if old_process is not None and old_process.poll() is None:
                old_process.terminate()
                try:
                    old_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    old_process.kill()
            self._stdout = ""
            self._published_stdout = ""
            self._active_prompt_raw = ""
            self._waiting = False
            self._closed = False
            self._model_mtime_ns = 0
            self.pending_draft = None
            self.turns = []
            self.input_history = []
            self._restoring = False
            self._launch_worker()
