from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from model_io import (
    model_name_from_payload,
    prepare_model_export,
    validate_model_payload,
)
from web_bridge import ChatTurn, SessionRegistry, TerminalProcessSession, _write_json_atomic


class ModelFileSession(TerminalProcessSession):
    """Terminal bridge session with a persistent loaded-model baseline and export support."""

    def __init__(
        self,
        project_dir: Path,
        runtime_dir: Path,
        *,
        initial_model: dict[str, Any] | None = None,
        model_name: str | None = None,
    ) -> None:
        self.base_model_path: Path | None = None
        self.model_name = str(model_name or "").strip() or None
        self._undo_preserved_turns: list[ChatTurn] | None = None
        runtime_path = Path(runtime_dir).resolve()
        runtime_path.mkdir(parents=True, exist_ok=True)
        if initial_model is not None:
            normalized = validate_model_payload(initial_model)
            self.model_name = self.model_name or model_name_from_payload(normalized) or None
            self.base_model_path = runtime_path / "loaded_model_base.json"
            _write_json_atomic(self.base_model_path, normalized)
        super().__init__(project_dir, runtime_dir)

    def _launch_worker(self) -> None:
        if self.base_model_path is None:
            return super()._launch_worker()

        command = [
            sys.executable,
            "-u",
            str(self.project_dir / "web_worker_resume.py"),
            "--model-path",
            str(self.model_path),
            "--load-model",
            str(self.base_model_path),
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

    @staticmethod
    def _turns_before_last_answer(turns: list[ChatTurn]) -> list[ChatTurn]:
        """Keep the visible conversation through the question being revisited.

        Undo removes the latest user answer and everything generated after it. The
        assistant question immediately before that answer is intentionally kept,
        so the browser can make it active again without rebuilding older rows.
        """
        for index in range(len(turns) - 1, -1, -1):
            if turns[index].role == "user":
                return list(turns[:index])
        return list(turns)

    def _publish_if_ready(self) -> None:
        """During replay, advance protocol state without recreating chat turns."""
        if not getattr(self, "_restoring", False):
            return super()._publish_if_ready()

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
            self._refresh_draft_state(clean)

    def send(
        self,
        value: str,
        *,
        display_value: str | None = None,
        record_history: bool = True,
    ) -> None:
        """Replay answers without appending duplicate visible user messages."""
        restoring = bool(getattr(self, "_restoring", False))
        with self._lock:
            visible_count = len(self.turns)
        super().send(
            value,
            display_value=display_value,
            record_history=record_history,
        )
        if restoring:
            with self._lock:
                del self.turns[visible_count:]
                self.pending_draft = None

    def _reset_runtime_for_replay(self) -> None:
        """Reset worker state while retaining the stable visible chat prefix."""
        preserved = list(self._undo_preserved_turns or [])
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
            self.turns = preserved
            self.process = None

    def undo_last_decision(self) -> None:
        """Fast rewind one user decision while preserving the visible chat.

        The current guided implementation still needs deterministic replay to
        rebuild the Python call stack. Replay is therefore kept as an internal
        mechanism, but it is silent and runs with AI disabled. This avoids both
        rebuilding every browser message and re-running conversational LLM calls.
        AI is restored only after the previous modeling question is reached.
        """
        self._publish_if_ready()
        with self._lock:
            if not self.input_history:
                raise RuntimeError("There is no previous user decision to undo.")
            prior_history = list(self.input_history[:-1])
            preserved_turns = self._turns_before_last_answer(self.turns)

        ai_state = self.ai_snapshot()
        active_ai_model = (
            ai_state.get("model")
            if ai_state.get("status") == "active"
            else None
        )

        self._append_diagnostic("\n\n--- WEB UNDO: fast silent replay ---\n")
        with self._lock:
            self._restoring = True
            self._undo_preserved_turns = preserved_turns

        try:
            self._terminate_worker()
            self._reset_runtime_for_replay()
            with self._lock:
                self.input_history = prior_history
                self._restoring = True

            # Rebuild the deterministic call stack first. AI is intentionally off
            # so historical questions are not conversationalized again.
            self._launch_worker()
            self._wait_until_waiting()

            for value, display_value in prior_history:
                self._wait_until_waiting()
                self.send(
                    value,
                    display_value=display_value,
                    record_history=False,
                )
                self._wait_until_waiting()

            # Keep the old visible wording of the question being revisited. The
            # worker's freshly reconstructed prompt still owns the interaction
            # contract/buttons through _active_prompt_raw.
            self._publish_if_ready()

            # Restore only the AI runtime state; no historical prompt is sent to
            # the model. The next new question can be conversationalized normally.
            if active_ai_model:
                self._wait_for_ai_model(str(active_ai_model))
        finally:
            with self._lock:
                self._undo_preserved_turns = None
                self._restoring = False

    def export_model(self, model_name: str) -> dict[str, Any]:
        try:
            payload = json.loads(self.model_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("The current model could not be prepared for saving.") from exc
        exported = prepare_model_export(payload, model_name)
        self.model_name = str(exported["graph"]["model_name"])
        return exported

    def model_snapshot(self) -> dict[str, Any]:
        snapshot = super().model_snapshot()
        if self.model_name:
            snapshot["name"] = self.model_name

        # Red/orange impact state is presentation metadata only. In particular,
        # rename_preview never substitutes the proposed name into the semantic
        # model projection before confirmation. The UI shows the current element
        # in red plus an explicit old -> proposed-new summary; a Yes answer then
        # commits the rename and all projections regenerate from the same stable ID.
        presentation: dict[str, Any] = {}
        try:
            payload = json.loads(self.model_path.read_text(encoding="utf-8"))
            graph_meta = payload.get("graph") if isinstance(payload, dict) else None
            candidate = graph_meta.get("_revision_presentation") if isinstance(graph_meta, dict) else None
            if isinstance(candidate, dict):
                presentation = candidate
        except (OSError, json.JSONDecodeError):
            presentation = {}
        snapshot["presentation"] = presentation
        return snapshot


class ModelFileSessionRegistry(SessionRegistry):
    def _create_unlocked(self) -> tuple[str, ModelFileSession]:
        session_id = uuid.uuid4().hex
        current = ModelFileSession(
            self.project_dir,
            self.runtime_root / session_id,
        )
        self._sessions[session_id] = current
        return session_id, current

    def _create_loaded_unlocked(
        self,
        payload: dict[str, Any],
        model_name: str,
    ) -> tuple[str, ModelFileSession]:
        session_id = uuid.uuid4().hex
        current = ModelFileSession(
            self.project_dir,
            self.runtime_root / session_id,
            initial_model=payload,
            model_name=model_name,
        )
        self._sessions[session_id] = current
        return session_id, current

    def load(
        self,
        session_id: str | None,
        payload: dict[str, Any],
        model_name: str,
    ) -> tuple[str, ModelFileSession]:
        with self._lock:
            old = self._sessions.pop(session_id, None) if session_id else None
            if old is not None:
                old.close()
            return self._create_loaded_unlocked(payload, model_name)
