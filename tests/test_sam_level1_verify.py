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
    def __init__(self, matches_by_name=None):
        self.matches_by_name = dict(matches_by_name or {})

    def find_elements_by_name(self, name):
        return list(self.matches_by_name.get(name, []))


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
        FakeManager.project = FakeProject()
        with self.assertRaises(SamLevel1SyncError):
            verify_level1_package(
                self.settings,
                "MBSE_Instance_Test_12345678",
                snapshot_digest="12345678",
                require_completion_marker=False,
                connector_class=FakeConnector,
                project_manager_class=FakeManager,
            )

    def test_legacy_verification_can_still_require_completion_marker(self):
        package_name = "MBSE_Instance_Test_12345678"
        FakeManager.project = FakeProject(
            {package_name: [FakeElement("sam-package-1")]}
        )
        with self.assertRaises(SamLevel1SyncError):
            verify_level1_package(
                self.settings,
                package_name,
                snapshot_digest="12345678",
                require_completion_marker=True,
                connector_class=FakeConnector,
                project_manager_class=FakeManager,
            )

    def test_managed_instance_uses_final_name_as_completion_proof(self):
        package_name = "MBSE_Instance_Test_12345678"
        FakeManager.project = FakeProject(
            {package_name: [FakeElement("sam-package-1")]}
        )
        result = verify_level1_package(
            self.settings,
            package_name,
            snapshot_digest="12345678",
            require_completion_marker=False,
            connector_class=FakeConnector,
            project_manager_class=FakeManager,
        )
        self.assertTrue(result["verified_in_sam"])
        self.assertEqual(result["verified_package_id"], "sam-package-1")
        self.assertIsNone(result["verified_completion_marker_id"])

    def test_verified_sync_adds_fresh_package_evidence_without_visible_marker(self):
        package_name = "MBSE_Instance_Test_12345678"
        FakeManager.project = FakeProject(
            {package_name: [FakeElement("sam-package-1")]}
        )
        upstream = {
            "status": "synced",
            "package_name": package_name,
            "snapshot_digest": "12345678",
            "completion_marker_required": False,
            "completion_marker_name": None,
            "sam_write_performed": True,
            "timings": {"write_seconds": 1.0},
        }
        with patch(
            "sam_level1_verify.sync_level1_to_sam_managed_direct",
            return_value=upstream.copy(),
        ):
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
        self.assertIsNone(result["verified_completion_marker_id"])
        self.assertEqual(result["sam_package_id"], "sam-package-1")
        self.assertIn("final_verification_seconds", result["timings"])
        self.assertIn("total_with_verification_seconds", result["timings"])


if __name__ == "__main__":
    unittest.main()
