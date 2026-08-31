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
from web_bridge import SessionRegistry, TerminalProcessSession, _write_json_atomic


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
