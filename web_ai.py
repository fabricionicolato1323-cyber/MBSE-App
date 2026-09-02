from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from llm_service import OllamaLLM

CONFIG_PATH = Path(__file__).resolve().with_name("config.json")


class LocalAIServiceError(RuntimeError):
    pass


def load_web_ai_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "base_url": "http://localhost:11434",
        "timeout_seconds": 120,
        "keep_alive": None,
        "num_ctx": None,
    }
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults

    ollama = data.get("ollama", {})
    if not isinstance(ollama, dict):
        return defaults

    result = dict(defaults)
    for key in result:
        if key in ollama:
            result[key] = ollama[key]
    return result


def normalize_base_url(base_url: str) -> str:
    normalized = str(base_url or "http://localhost:11434").strip().rstrip("/")
    if normalized.endswith("/api"):
        normalized = normalized[:-4]
    return normalized or "http://localhost:11434"


def list_installed_models(
    *,
    base_url: str = "http://localhost:11434",
    timeout_seconds: float = 5.0,
) -> list[str]:
    """Return models reported by the local Ollama installation.

    Discovery is intentionally independent from OllamaLLM construction because
    OllamaLLM requires one model to be selected when several are installed.
    """
    request = urllib.request.Request(
        f"{normalize_base_url(base_url)}/api/tags",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise LocalAIServiceError("The local AI service is unavailable.") from exc

    if not isinstance(payload, dict):
        raise LocalAIServiceError("The local AI service returned an invalid response.")

    models: list[str] = []
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name and name not in models:
            models.append(name)
    return models


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


class AIControlManager:
    """Apply web AI enable/disable requests to one running OAApp session."""

    def __init__(
        self,
        app: Any,
        runtime_dir: Path,
        *,
        config: dict[str, Any] | None = None,
        client_factory: Callable[..., Any] = OllamaLLM,
        poll_seconds: float = 0.2,
    ) -> None:
        self.app = app
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.command_path = self.runtime_dir / "ai_command.json"
        self.status_path = self.runtime_dir / "ai_status.json"
        self.config = dict(config or load_web_ai_config())
        self.client_factory = client_factory
        self.poll_seconds = poll_seconds
        self._last_request_id = ""
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _status(
        self,
        status: str,
        *,
        model: str | None = None,
        message: str = "",
    ) -> None:
        write_json_atomic(
            self.status_path,
            {
                "status": status,
                "model": model,
                "message": message,
            },
        )

    def start(self) -> None:
        # Web sessions intentionally start in deterministic mode. Selecting a
        # model is an explicit user action and never inferred from installation.
        self.app.llm = None
        self._status("off", message="AI assistance is off.")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(0.5, self.poll_seconds * 4))

    def _read_command(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.command_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def process_pending_once(self) -> bool:
        payload = self._read_command()
        if not payload:
            return False

        request_id = str(payload.get("request_id", "")).strip()
        if not request_id or request_id == self._last_request_id:
            return False
        self._last_request_id = request_id

        action = str(payload.get("action", "")).strip().casefold()
        if action == "disable":
            self.app.llm = None
            self._status("off", message="AI assistance is off.")
            return True

        if action != "activate":
            self._status("error", message="Unsupported AI control request.")
            return True

        model = str(payload.get("model", "")).strip()
        if not model:
            self._status("error", message="Select a local model before activating AI.")
            return True

        self._status("activating", model=model, message="Activating AI assistance…")
        try:
            client = self.client_factory(
                base_url=normalize_base_url(str(self.config.get("base_url", ""))),
                model=model,
                timeout_seconds=float(self.config.get("timeout_seconds", 120)),
                keep_alive=self.config.get("keep_alive"),
                num_ctx=self.config.get("num_ctx"),
            )
        except Exception:
            self.app.llm = None
            self._status(
                "error",
                model=None,
                message="The selected local AI model could not be activated.",
            )
            return True

        self.app.llm = client
        self._status(
            "active",
            model=model,
            message=f"AI assistance is active with {model}.",
        )
        return True

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_seconds):
            self.process_pending_once()
