import unittest

import web_app


class FakeWorker:
    def __init__(self, name):
        self.name = name

    def state(self):
        return {
            "turns": [{"id": self.name, "role": "assistant", "content": "Question"}],
            "waiting": True,
            "closed": False,
            "buttons": [],
            "model": {
                "nodes": [],
                "edges": [],
                "counts": {"nodes": 0, "edges": 0},
                "drafts": [],
            },
        }


class FakeRegistry:
    def __init__(self):
        self.counter = 0
        self.sessions = {}

    def create(self):
        self.counter += 1
        sid = f"session-{self.counter}"
        worker = FakeWorker(sid)
        self.sessions[sid] = worker
        return sid, worker

    def get(self, sid):
        return self.sessions.get(sid)

    def reset(self, sid):
        self.sessions.pop(sid, None)
        return self.create()


class WebSessionTests(unittest.TestCase):
    def setUp(self):
        self.previous_registry = web_app.registry
        web_app.registry = FakeRegistry()
        web_app.app.config.update(TESTING=True, SECRET_KEY="test")
        self.client = web_app.app.test_client()

    def tearDown(self):
        web_app.registry = self.previous_registry

    def test_reset_changes_session_identity(self):
        self.client.get("/")
        first = self.client.get("/api/state")
        self.assertEqual(first.status_code, 200)
        first_id = first.get_json()["session_id"]

        reset = self.client.post("/api/reset")
        self.assertEqual(reset.status_code, 200)
        second_id = reset.get_json()["session_id"]
        self.assertNotEqual(first_id, second_id)

        second = self.client.get("/api/state")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.get_json()["session_id"], second_id)

    def test_stale_state_request_does_not_create_replacement_session(self):
        self.client.get("/")
        state = self.client.get("/api/state").get_json()
        old_id = state["session_id"]
        web_app.registry.sessions.pop(old_id)

        stale = self.client.get("/api/state")
        self.assertEqual(stale.status_code, 409)
        self.assertTrue(stale.get_json()["stale_session"])
        self.assertEqual(web_app.registry.counter, 1)


if __name__ == "__main__":
    unittest.main()
