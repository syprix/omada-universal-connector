from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_ineligible_interference_ap_summary import (
    SiteIneligibleInterferenceApError, summarize_site_ineligible_interference_aps,
)


class IneligibleInterferenceApProjectionTests(unittest.TestCase):
    def test_counts_valid_macs_without_returning_them(self) -> None:
        result = summarize_site_ineligible_interference_aps({
            "macList": ["00-11-22-33-44-55", "00:11:22:33:44:66"]})
        self.assertEqual(result["data"], {
            "reported_ap_count": 2, "valid_ap_count": 2, "truncated": False})
        self.assertFalse(result["partial"])
        self.assertNotIn("00-11-22-33-44-55", repr(result))

    def test_invalid_unknown_missing_and_truncated_data_are_partial(self) -> None:
        result = summarize_site_ineligible_interference_aps({
            "macList": ["not-a-mac", None], "future": True})
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        missing = summarize_site_ineligible_interference_aps({})
        self.assertEqual(missing["missing_field_count"], 1)
        self.assertTrue(missing["partial"])
        truncated = summarize_site_ineligible_interference_aps(
            {"macList": ["00-11-22-33-44-55"] * 501})
        self.assertTrue(truncated["data"]["truncated"])
        self.assertTrue(truncated["partial"])

    def test_rejects_malformed_outer_response(self) -> None:
        for value in (None, [], {"macList": None}):
            with self.subTest(value=value), self.assertRaises(
                    SiteIneligibleInterferenceApError):
                summarize_site_ineligible_interference_aps(value)


class IneligibleInterferenceApClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "9" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path_and_returns_summary(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "macList": ["00-11-22-33-44-55"]}}) as request:
            result = self.client.read_site_ineligible_interference_ap_summary(
                self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/full-channel-detect/batch/info",
            token="token")
        self.assertEqual(result["data"]["valid_ap_count"], 1)
        self.assertNotIn("00-11-22-33-44-55", repr(result))

    def test_rejects_invalid_result_and_binds_controller(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_ineligible_interference_ap_summary(self.site_ref)
        self.assertTrue(self.client._site_ineligible_interference_ap_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/full-channel-detect/batch/info"))
        self.assertFalse(self.client._site_ineligible_interference_ap_request_valid(
            "/openapi/v1/other/sites/site_internal/full-channel-detect/batch/info"))


if __name__ == "__main__":
    unittest.main()
