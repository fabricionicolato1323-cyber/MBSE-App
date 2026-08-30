from __future__ import annotations

import unittest
from unittest.mock import patch

from sam_connection import SamSettings
from sam_level1_sync import SamLevel1SyncError
from sam_level1_verify import sync_level1_to_sam_verified, verify_level1_package


class FakeElement:
    def __init__(self, element_id: str):
        self._id = element_id


class FakeProject:
    def __init__(self, matches=None):
        self.matches = list(matches or [])

    def find_elements_by_name(self, name):
        return list(self.matches)


class FakeConnector:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeManager:
    project = FakeProject()

    def __init__(self, connector):
        self.connector = connector

    def get_scripting_project(self, project_id):
        return type(self).project


class SamLevel1VerificationTests(unittest.TestCase):
    def setUp(self):
        self.settings = SamSettings(
            server_url="https://sam.example.test",
            organization_id="org",
            project_id="project",
            access_token="secret",
            use_ssl=True,
        )

    def test_verify_requires_package_to_exist_after_reload(self):
        FakeManager.project = FakeProject([])
        with self.assertRaises(SamLevel1SyncError):
            verify_level1_package(
                self.settings,
                "MBSE_Level1_Test_12345678",
                connector_class=FakeConnector,
                project_manager_class=FakeManager,
            )

    def test_verified_sync_adds_fresh_package_evidence(self):
        FakeManager.project = FakeProject([FakeElement("sam-package-1")])
        upstream = {
            "status": "synced",
            "package_name": "MBSE_Level1_Test_12345678",
            "snapshot_digest": "12345678",
            "sam_write_performed": True,
        }
        with patch("sam_level1_verify.sync_level1_to_sam", return_value=upstream.copy()):
            result = sync_level1_to_sam_verified(
                {"nodes": [{"id": "x"}]},
                scenarios=[],
                settings=self.settings,
                expected_digest="12345678",
                connector_class=FakeConnector,
                project_manager_class=FakeManager,
                factory_class=object,
            )

        self.assertTrue(result["verified_in_sam"])
        self.assertEqual(result["verified_package_id"], "sam-package-1")
        self.assertEqual(result["sam_package_id"], "sam-package-1")


if __name__ == "__main__":
    unittest.main()
