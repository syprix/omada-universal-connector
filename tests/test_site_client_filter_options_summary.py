from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_client_filter_options_summary import (
    ClientFilterOptionsError, project_site_client_filter_options_summary,
)

SITE_REF = "a" * 24


class ClientFilterOptionsProjectionTests(unittest.TestCase):
    def test_counts_categories_and_device_details_without_labels(self) -> None:
        result = project_site_client_filter_options_summary({
            "deviceType": [{"category": "private-category", "type": ["phone", "tablet"]}],
            "vendor": ["private-vendor"], "device": ["private-device"],
            "network": ["private-network"], "ssid": ["private-ssid"],
            "deviceDetail": [{"mac": "private-mac", "name": "private-name",
                              "stack": True, "stackName": "private-stack"},
                             {"stack": False}],
        })
        self.assertEqual(result["device_type_categories"], 1)
        self.assertEqual(result["device_type_values"], 2)
        self.assertEqual(result["vendors"], 1)
        self.assertEqual(result["devices"], 1)
        self.assertEqual(result["networks"], 1)
        self.assertEqual(result["ssids"], 1)
        self.assertEqual(result["device_details"], 2)
        self.assertEqual(result["stacked_devices"], 1)
        self.assertFalse(result["partial"])
        for secret in ("private-category", "private-vendor", "private-device", "private-network",
                       "private-ssid", "private-mac", "private-name", "private-stack", "phone"):
            self.assertNotIn(secret, repr(result))

    def test_missing_unknown_and_invalid_fields_mark_partial(self) -> None:
        result = project_site_client_filter_options_summary({
            "deviceType": [{"category": "hidden", "type": "bad", "extra": "hidden"}],
            "vendor": [5], "device": [], "network": [], "ssid": [],
            "deviceDetail": [{"stack": "yes"}], "other": "private",
        })
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["unknown_field_count"], 2)
        self.assertGreaterEqual(result["invalid_field_count"], 2)
        self.assertNotIn("hidden", repr(result))
        self.assertNotIn("private", repr(result))

    def test_malformed_top_level_fails_and_bad_lists_mark_partial(self) -> None:
        for raw in (None, []):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ClientFilterOptionsError):
                project_site_client_filter_options_summary(raw)
        for raw in ({"vendor": "bad"}, {"vendor": ["x"] * 10001}):
            result = project_site_client_filter_options_summary(raw)
            self.assertTrue(result["partial"])
            self.assertGreaterEqual(result["invalid_field_count"], 1)
            self.assertEqual(result["vendors"], 0)


class ClientFilterOptionsClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site-1"

    def test_reads_fixed_site_route_and_redacts_option_values(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "deviceType": [], "vendor": ["secret"], "device": [], "network": [],
                    "ssid": [], "deviceDetail": []}}) as request:
            result = self.client.read_site_client_filter_options_summary(SITE_REF)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-1/clients/search-fields-options", token="token")
        self.assertEqual(result["vendors"], 1)
        self.assertNotIn("secret", repr(result))

    def test_unknown_site_and_unapproved_query_fail_before_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_client_filter_options_summary("b" * 24)
        request.assert_not_called()
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/ctrl/sites/site-1/clients/search-fields-options?searchKey=x")
