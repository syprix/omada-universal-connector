from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_longest_client_uptime import summarize_longest_client_uptime


class LongestClientUptimeTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_documented_values_keep_source_names_without_interpretation(self):
        result = summarize_longest_client_uptime(
            {"total": 13, "wiredClient": 4, "wirelessClient": 9})
        self.assertEqual(result["total"], 13)
        self.assertEqual(result["wiredClient"], 4)
        self.assertEqual(result["wirelessClient"], 9)
        self.assertFalse(result["partial"])

    def test_malformed_missing_and_unknown_values_mark_partial(self):
        result = summarize_longest_client_uptime(
            {"total": True, "wiredClient": 2_147_483_648, "extra": "omit"})
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])

    def test_fixed_site_bound_path_and_malformed_response(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "total": 3, "wiredClient": 1, "wirelessClient": 2}}) as request:
            result = self.client.read_site_longest_client_uptime_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/dashboard/longest-uptime",
            token="token")
        self.assertEqual(result["total"], 3)
        path = "/openapi/v1/ctrl/sites/site_internal/dashboard/longest-uptime"
        self.assertTrue(self.client._site_longest_client_uptime_request_valid(path))
        self.assertFalse(self.client._site_longest_client_uptime_request_valid(
            path.replace("/ctrl/", "/other/")))
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_longest_client_uptime_summary(self.site_ref)


if __name__ == "__main__":
    unittest.main()
