import json
import tempfile
import unittest
from pathlib import Path

import web_app


SAMPLE_MODEL = {
    "directed": True,
    "multigraph": True,
    "graph": {"model": "Arcadia Operational Analysis"},
    "nodes": [
        {"id": "g1", "type": "OperationalCapability", "name": "Protect area"},
        {
            "id": "p1",
            "type": "OperationalActor",
            "name": "Operator",
            "nature": "human_individual",
        },
        {"id": "a1", "type": "OperationalActivity", "name": "Monitor area"},
    ],
    "edges": [
        {"source": "p1", "target": "a1", "key": 0, "type": "PERFORMS"},
        {"source": "a1", "target": "g1", "key": 0, "type": "SUPPORTS_CAPABILITY"},
    ],
}


class FakeFileWorker:
    def __init__(self, model=None, model_name=""):
        self.model = model or SAMPLE_MODEL
        self.model_name = model_name
        self.runtime_dir = Path(tempfile.mkdtemp(prefix="mbse-test-model-file-"))
        self.model_path = self.runtime_dir / "model.json"
        self.model_path.write_text(
            json.dumps(self.model),
            encoding="utf-8",
        )

    def state(self):
        return {
            "turns": [],
            "waiting": True,
            "closed": False,
            "buttons": [],
            "interaction": {"mode": "free_text", "choices": []},
            "model": {
                "nodes": [],
                "edges": [],
                "counts": {"nodes": 0, "edges": 0},
                "drafts": [],
            },
            "ai": {
                "status": "off",
                "model": None,
                "message": "AI assistance is off.",
            },
            "can_undo": False,
        }

    def export_model(self, model_name):
        from model_io import prepare_model_export

        self.model_name = model_name
        return prepare_model_export(self.model, model_name)


class FakeFileRegistry:
    def __init__(self):
        self.counter = 0
        self.sessions = {}

    def create(self):
        self.counter += 1
        sid = f"session-{self.counter}"
        worker = FakeFileWorker()
        self.sessions[sid] = worker
        return sid, worker

    def get(self, sid):
        return self.sessions.get(sid)

    def reset(self, sid):
        self.sessions.pop(sid, None)
        return self.create()

    def load(self, sid, payload, model_name):
        self.sessions.pop(sid, None)
        self.counter += 1
        new_sid = f"session-{self.counter}"
        worker = FakeFileWorker(payload, model_name)
        self.sessions[new_sid] = worker
        return new_sid, worker


class WebModelFileTests(unittest.TestCase):
    def setUp(self):
        self.previous_registry = web_app.registry
        web_app.registry = FakeFileRegistry()
        web_app.app.config.update(TESTING=True, SECRET_KEY="test")
        self.client = web_app.app.test_client()
        self.client.get("/")

    def tearDown(self):
        web_app.registry = self.previous_registry

    def test_export_requires_and_embeds_model_name(self):
        response = self.client.post(
            "/api/model/export",
            json={"model_name": "Perimeter protection"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["model_name"], "Perimeter protection")
        self.assertEqual(
            payload["model"]["graph"]["model_name"],
            "Perimeter protection",
        )

    def test_load_replaces_session_and_uses_filename_when_name_is_missing(self):
        first_id = self.client.get("/api/state").get_json()["session_id"]
        response = self.client.post(
            "/api/model/load",
            json={"model": SAMPLE_MODEL, "file_name": "Saved OA.json"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertNotEqual(payload["session_id"], first_id)
        self.assertEqual(payload["model_name"], "Saved OA")
        self.assertEqual(payload["counts"], {"nodes": 3, "edges": 2})

    def test_load_rejects_invalid_model(self):
        response = self.client.post(
            "/api/model/load",
            json={"model": {"nodes": [], "edges": "bad"}, "file_name": "bad.json"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a supported", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
