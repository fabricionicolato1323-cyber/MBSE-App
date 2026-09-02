import unittest

from sam_connection import (
    SamConfigurationError,
    SamSettings,
    run_connection_test,
    settings_from_env,
)


class FakeConnector:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeElement:
    def __init__(self, element_id, name, element_type="Package"):
        self._id = element_id
        self._name = name
        self._element_type = element_type


class FakeProject:
    def __init__(self, project_id):
        self._project_id = project_id
        self._root = FakeElement("root-1", "API Test")

    def get_id(self):
        return self._project_id

    def get_name(self):
        return "API Test"

    def get_root_package(self):
        return self._root

    def get_root(self):
        return [self._root, FakeElement("diagram-1", "Diagrams")]


class FakeProjectManager:
    last_connector = None
    last_project_id = None
    calls = []

    def __init__(self, connector):
        type(self).last_connector = connector

    def get_projects(self):
        type(self).calls.append("get_projects")
        return [
            {
                "@id": "project-1",
                "name": "API Test",
                "description": "Connection test project",
            }
        ]

    def get_scripting_project(self, project_id):
        type(self).calls.append("get_scripting_project")
        type(self).last_project_id = project_id
        return FakeProject(project_id)


class SamConnectionTests(unittest.TestCase):
    def setUp(self):
        FakeProjectManager.last_connector = None
        FakeProjectManager.last_project_id = None
        FakeProjectManager.calls = []

    def test_missing_required_configuration_is_rejected(self):
        with self.assertRaises(SamConfigurationError) as ctx:
            settings_from_env({}, load_dotenv=False)
        self.assertIn("SAM_SERVER_URL", str(ctx.exception))
        self.assertIn("SAM_ACCESS_TOKEN", str(ctx.exception))

    def test_settings_are_loaded_and_server_url_is_normalized(self):
        settings = settings_from_env(
            {
                "SAM_SERVER_URL": "https://sam.example.test/",
                "SAM_ORGANIZATION_ID": "org-1",
                "SAM_PROJECT_ID": "project-1",
                "SAM_ACCESS_TOKEN": "secret",
                "SAM_USE_SSL": "true",
            },
            load_dotenv=False,
        )
        self.assertEqual(settings.server_url, "https://sam.example.test")
        self.assertTrue(settings.use_ssl)

    def test_invalid_ssl_flag_is_rejected(self):
        with self.assertRaises(SamConfigurationError):
            settings_from_env(
                {
                    "SAM_SERVER_URL": "https://sam.example.test",
                    "SAM_ORGANIZATION_ID": "org-1",
                    "SAM_PROJECT_ID": "project-1",
                    "SAM_ACCESS_TOKEN": "secret",
                    "SAM_USE_SSL": "sometimes",
                },
                load_dotenv=False,
            )

    def test_connection_test_lists_organization_before_loading_project(self):
        settings = SamSettings(
            server_url="https://sam.example.test",
            organization_id="org-1",
            project_id="project-1",
            access_token="secret",
            use_ssl=True,
        )
        result = run_connection_test(
            settings,
            connector_class=FakeConnector,
            project_manager_class=FakeProjectManager,
        )
        self.assertEqual(
            FakeProjectManager.calls,
            ["get_projects", "get_scripting_project"],
        )
        connector = FakeProjectManager.last_connector
        self.assertEqual(connector.kwargs["organization_id"], settings.organization_id)
        self.assertEqual(FakeProjectManager.last_project_id, settings.project_id)
        self.assertTrue(result["project_loaded"])
        self.assertFalse(result["project_selection_required"])
        self.assertEqual(result["project_id"], "project-1")
        self.assertEqual(result["project_name"], "API Test")
        self.assertEqual(result["root_package_id"], "root-1")
        self.assertEqual(len(result["available_projects"]), 1)
        self.assertFalse(result["write_performed"])

    def test_stale_configured_project_returns_project_picker_discovery(self):
        settings = SamSettings(
            server_url="https://sam.example.test",
            organization_id="org-1",
            project_id="old-project-id",
            access_token="secret",
        )
        result = run_connection_test(
            settings,
            connector_class=FakeConnector,
            project_manager_class=FakeProjectManager,
        )
        self.assertEqual(FakeProjectManager.calls, ["get_projects"])
        self.assertIsNone(FakeProjectManager.last_project_id)
        self.assertFalse(result["project_loaded"])
        self.assertTrue(result["project_selection_required"])
        self.assertEqual(result["configured_project_id"], "old-project-id")
        self.assertEqual(result["project_id"], "")
        self.assertEqual(result["available_projects"][0]["id"], "project-1")
        self.assertFalse(result["write_performed"])

    def test_result_never_contains_access_token(self):
        settings = SamSettings(
            server_url="https://sam.example.test",
            organization_id="org-1",
            project_id="project-1",
            access_token="super-secret-token",
        )
        result = run_connection_test(
            settings,
            connector_class=FakeConnector,
            project_manager_class=FakeProjectManager,
        )
        self.assertNotIn("access_token", result)
        self.assertNotIn("super-secret-token", repr(result))


if __name__ == "__main__":
    unittest.main()
