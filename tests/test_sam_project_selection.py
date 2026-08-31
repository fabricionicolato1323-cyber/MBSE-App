from __future__ import annotations

import unittest

from flask import Flask

from sam_connection import SamSettings, list_available_projects, settings_from_env


class FakeConnector:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeProjectManager:
    def __init__(self, connector):
        self.connector = connector

    def get_projects(self):
        return [
            {"@id": "p2", "name": "Zulu", "description": "Second"},
            {"@id": "p1", "name": "Alpha", "description": "First"},
            {"name": "Missing id"},
        ]


class SamProjectSelectionTests(unittest.TestCase):
    def test_available_projects_are_normalized_and_sorted(self) -> None:
        settings = SamSettings(
            server_url="https://sam.example",
            organization_id="org",
            project_id="p1",
            access_token="token",
        )
        projects = list_available_projects(
            settings,
            connector_class=FakeConnector,
            project_manager_class=FakeProjectManager,
        )
        self.assertEqual(
            projects,
            [
                {"id": "p1", "name": "Alpha", "description": "First"},
                {"id": "p2", "name": "Zulu", "description": "Second"},
            ],
        )

    def test_query_project_selection_overrides_configured_default(self) -> None:
        flask_app = Flask(__name__)
        environ = {
            "SAM_SERVER_URL": "https://sam.example",
            "SAM_ORGANIZATION_ID": "org",
            "SAM_PROJECT_ID": "default-project",
            "SAM_ACCESS_TOKEN": "token",
        }
        with flask_app.test_request_context("/api/sam/level1/plan?project_id=chosen-project"):
            settings = settings_from_env(environ=environ, load_dotenv=False)
        self.assertEqual(settings.project_id, "chosen-project")

    def test_posted_project_selection_overrides_configured_default(self) -> None:
        flask_app = Flask(__name__)
        environ = {
            "SAM_SERVER_URL": "https://sam.example",
            "SAM_ORGANIZATION_ID": "org",
            "SAM_PROJECT_ID": "default-project",
            "SAM_ACCESS_TOKEN": "token",
        }
        with flask_app.test_request_context(
            "/api/sam/level1/send",
            method="POST",
            json={"project_id": "chosen-project"},
        ):
            settings = settings_from_env(environ=environ, load_dotenv=False)
        self.assertEqual(settings.project_id, "chosen-project")


if __name__ == "__main__":
    unittest.main()
