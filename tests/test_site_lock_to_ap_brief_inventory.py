from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_lock_to_ap_brief_inventory import (
    SiteLockToApBriefInventoryError, summarize_site_lock_to_ap_brief_inventory,
)


class SiteLockToApBriefInventoryTests(unittest.TestCase):
    def test_projects_status_and_support_counts_without_device_identity(self) -> None:
        result = summarize_site_lock_to_ap_brief_inventory([
            {"mac": "private-mac", "name": "AP name", "ip": "192.0.2.8",
             "model": "EAP-example", "statusCategory": 1, "status": 14,
             "active": True, "supportLockToAp": True},
            {"statusCategory": 3, "status": 31, "active": False,
             "supportLockToAp": False},
        ])
        self.assertEqual(result["data"]["reported_ap_count"], 2)
        self.assertEqual(result["data"]["status_category_counts"]["1"], 1)
        self.assertEqual(result["data"]["status_counts"]["31"], 1)
        self.assertEqual(result["data"]["lock_to_ap_support_counts"], {
            "supported_count": 1, "unsupported_count": 1, "unreported_count": 0})
        self.assertFalse(result["partial"])
        for value in ("private-mac", "AP name", "192.0.2.8", "EAP-example"):
            self.assertNotIn(value, repr(result))

    def test_invalid_unknown_unknown_codes_and_truncation_mark_partial(self) -> None:
        result = summarize_site_lock_to_ap_brief_inventory([
            {"statusCategory": 9, "status": 99, "active": "yes",
             "supportLockToAp": False, "future": True}, None,
        ])
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["data"]["unknown_status_category_count"], 1)
        self.assertEqual(result["data"]["unknown_status_count"], 1)
        self.assertTrue(result["partial"])
        large = summarize_site_lock_to_ap_brief_inventory([{}] * 501)
        self.assertEqual(large["data"]["valid_ap_record_count"], 500)
        self.assertTrue(large["data"]["truncated"])
        self.assertTrue(large["partial"])

    def test_rejects_non_list_response(self) -> None:
        with self.assertRaises(SiteLockToApBriefInventoryError):
            summarize_site_lock_to_ap_brief_inventory({})


class SiteLockToApBriefClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "7" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path_and_projects_result(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": [
                    {"statusCategory": 1, "status": 14,
                     "supportLockToAp": True}]}) as request:
            result = self.client.read_site_lock_to_ap_brief_inventory(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v2/ctrl/sites/site_internal/lockToAp/aps",
            token="token")
        self.assertEqual(result["data"]["lock_to_ap_support_counts"]["supported_count"], 1)

    def test_rejects_invalid_result_and_binds_controller(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_lock_to_ap_brief_inventory(self.site_ref)
        self.assertTrue(self.client._site_lock_to_ap_brief_request_valid(
            "/openapi/v2/ctrl/sites/site_internal/lockToAp/aps"))
        self.assertFalse(self.client._site_lock_to_ap_brief_request_valid(
            "/openapi/v2/other/sites/site_internal/lockToAp/aps"))


if __name__ == "__main__":
    unittest.main()
