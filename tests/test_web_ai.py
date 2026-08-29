import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from web_ai import AIControlManager, list_installed_models, write_json_atomic


class FakeApp:
    def __init__(self):
        self.llm = "startup-client"


class FakeClient:
    def __init__(self, **kwargs):
        self.model = kwargs["model"]
        self.kwargs = kwargs


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def read_status(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_model_discovery_uses_local_tags_without_selecting_a_model():
    response = FakeResponse(
        {
            "models": [
                {"name": "model-a:latest"},
                {"model": "model-b:small"},
            ]
        }
    )
    with patch("web_ai.urllib.request.urlopen", return_value=response):
        assert list_installed_models(timeout_seconds=1) == [
            "model-a:latest",
            "model-b:small",
        ]


def test_web_session_starts_with_ai_off_and_requires_explicit_activation():
    with TemporaryDirectory() as temp:
        app = FakeApp()
        manager = AIControlManager(
            app,
            Path(temp),
            client_factory=FakeClient,
            poll_seconds=10,
        )
        manager.start()
        try:
            assert app.llm is None
            status = read_status(manager.status_path)
            assert status["status"] == "off"
            assert status["model"] is None
        finally:
            manager.stop()


def test_activate_and_disable_change_only_the_session_ai_client():
    with TemporaryDirectory() as temp:
        app = FakeApp()
        manager = AIControlManager(
            app,
            Path(temp),
            client_factory=FakeClient,
            poll_seconds=10,
        )
        manager.start()
        try:
            write_json_atomic(
                manager.command_path,
                {
                    "request_id": "activate-1",
                    "action": "activate",
                    "model": "selected-local-model",
                },
            )
            assert manager.process_pending_once() is True
            assert isinstance(app.llm, FakeClient)
            assert app.llm.model == "selected-local-model"
            assert read_status(manager.status_path)["status"] == "active"

            write_json_atomic(
                manager.command_path,
                {
                    "request_id": "disable-1",
                    "action": "disable",
                },
            )
            assert manager.process_pending_once() is True
            assert app.llm is None
            assert read_status(manager.status_path)["status"] == "off"
        finally:
            manager.stop()
