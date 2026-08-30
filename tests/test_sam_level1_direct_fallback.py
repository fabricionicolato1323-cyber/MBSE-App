from __future__ import annotations

import unittest
from unittest.mock import patch

from sam_connection import SamSettings
from sam_level1_sync import SamLevel1SyncError
from sam_level1_verify import sync_level1_to_sam_verified


class SamLevel1DirectFallbackTests(unittest.TestCase):
    def setUp(self):
        self.settings = SamSettings(
            server_url="https://sam.example.test",
            organization_id="org-1",
            project_id="project-1",
            access_token="secret",
            use_ssl=True,
        )
        self.payload = {
            "graph": {"model_name": "Fallback test"},
            "nodes": [],
            "edges": [],
        }

    @patch("sam_level1_verify.verify_level1_package")
    @patch("sam_level1_verify.sync_level1_to_sam_direct")
    @patch("sam_level1_verify.sync_level1_to_sam_transactional")
    def test_zero_artifact_transaction_falls_back_to_verified_direct_create(
        self,
        transactional,
        direct,
        verify,
    ):
        transactional.side_effect = SamLevel1SyncError(
            "SAM accepted the ArcadiaOA library transaction, but an uncached server "
            "verification did not find a complete managed library. Diagnostic: "
            "package=no; marker=no; marker_scoped=no; namespace=no; "
            "missing=OperationalEntity"
        )
        direct.return_value = {
            "status": "synced",
            "mode": "verified_direct_create_snapshot",
            "package_name": "MBSE_Level1_Fallback_test_12345678",
            "snapshot_digest": "12345678abcdef",
            "completion_marker_name": "MBSE_Level1_Complete_12345678",
            "timings": {"total_seconds": 1.0},
        }
        verify.return_value = {
            "verified_in_sam": True,
            "verified_package_name": "MBSE_Level1_Fallback_test_12345678",
            "verified_package_id": "server-package-id",
            "verified_match_count": 1,
            "verified_completion_marker_name": "MBSE_Level1_Complete_12345678",
            "verified_completion_marker_id": "server-marker-id",
        }

        result = sync_level1_to_sam_verified(
            self.payload,
            scenarios=[],
            settings=self.settings,
            expected_digest="12345678abcdef",
        )

        direct.assert_called_once()
        verify.assert_called_once()
        self.assertEqual(result["status"], "synced")
        self.assertTrue(result["verified_in_sam"])
        self.assertEqual(result["sam_package_id"], "server-package-id")
        self.assertTrue(result["transport_fallback"]["used"])
        self.assertEqual(
            result["transport_fallback"]["to"],
            "verified_direct_create_snapshot",
        )

    @patch("sam_level1_verify.sync_level1_to_sam_direct")
    @patch("sam_level1_verify.sync_level1_to_sam_transactional")
    def test_partial_transaction_never_triggers_direct_fallback(
        self,
        transactional,
        direct,
    ):
        transactional.side_effect = SamLevel1SyncError(
            "SAM accepted the ArcadiaOA library transaction, but an uncached server "
            "verification did not find a complete managed library. Diagnostic: "
            "package=yes; marker=no; marker_scoped=no; namespace=yes; "
            "missing=OperationalEntity"
        )

        with self.assertRaises(SamLevel1SyncError):
            sync_level1_to_sam_verified(
                self.payload,
                scenarios=[],
                settings=self.settings,
                expected_digest="12345678abcdef",
            )

        direct.assert_not_called()


if __name__ == "__main__":
    unittest.main()
