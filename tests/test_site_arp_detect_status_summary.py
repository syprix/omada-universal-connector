from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_arp_detect_status_summary import (
    SiteArpDetectStatusSummaryError,
    project_site_arp_detect_status_summary,
)


class SiteArpDetectStatusProjectionTests(unittest.TestCase):
    def test_projects_only_documented_boolean_flags(self) -> None:
        result = project_site_arp_detect_status_summary({
            "arpDetectEnable": True, "snoopForEntryEnable": False,
        })
        self.assertEqual(result["data"], {
            "arp_detection_enabled": True,
            "snoop_for_entry_enabled": False,
        })
        self.assertFalse(result["partial"])

    def test_counts_missing_invalid_and_unknown_without_echoing_values(self) -> None:
        result = project_site_arp_detect_status_summary({
            "arpDetectEnable": "private-value", "unexpected": "private-extra",
        })
        self.assertEqual(result["data"], {
            "arp_detection_enabled": None,
            "snoop_for_entry_enabled": None,
        })
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private", repr(result))

    def test_rejects_wrong_or_oversized_shapes(self) -> None:
        for value in (None, [], {str(index): True for index in range(9)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(
                    SiteArpDetectStatusSummaryError):
                project_site_arp_detect_status_summary(value)


class SiteArpDetectStatusClientTests(unittest.TestCase):
    def test_reads_fixed_site_bound_path_and_projects_response(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref = "a" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "arpDetectEnable": True, "snoopForEntryEnable": False,
                    "privateLabel": "must-not-escape",
                }}) as request:
            result = client.read_site_arp_detect_status_summary(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/arpDetects/status",
            token="test-token")
        self.assertEqual(result["resource"], "site_arp_detect_status_summary")
        self.assertEqual(result["site_ref"], site_ref)
        self.assertTrue(result["data"]["arp_detection_enabled"])
        self.assertNotIn("must-not-escape", repr(result))


if __name__ == "__main__":
    unittest.main()
