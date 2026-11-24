from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wifi_calling_profiles_summary import (
    WifiCallingProfilesError, project_site_wifi_calling_profiles_summary,
)

SITE_REF = "a" * 24


class WifiCallingProfilesProjectionTests(unittest.TestCase):
    def test_counts_profiles_carriers_and_endpoint_codes_without_values(self) -> None:
        result = project_site_wifi_calling_profiles_summary([
            {"id": "secret-id", "name": "private-profile", "description": "private-desc",
             "resource": 1, "carrierList": [
                 {"carrierName": "private-carrier", "epdgs": [
                     {"type": 0, "domain": "private.example", "qosPriority": 3},
                     {"type": 1, "ip": "192.0.2.1", "qosPriority": 3},
                 ]},
             ]},
        ])
        self.assertEqual(result["profile_count"], 1)
        self.assertEqual(result["carrier_count"], 1)
        self.assertEqual(result["epdg_count"], 2)
        self.assertEqual(result["epdg_type_counts"], {"domain": 1, "ip": 1, "unknown": 0})
        self.assertEqual(result["domain_endpoint_count"], 1)
        self.assertEqual(result["ip_endpoint_count"], 1)
        self.assertEqual(result["qos_priority_counts"], {"3": 2})
        self.assertEqual(result["profile_resource_counts"], {"1": 1})
        self.assertFalse(result["partial"])
        for secret in ("secret-id", "private-profile", "private-desc", "private-carrier",
                       "private.example", "192.0.2.1"):
            self.assertNotIn(secret, repr(result))

    def test_missing_and_unknown_fields_mark_partial(self) -> None:
        result = project_site_wifi_calling_profiles_summary([
            {"name": "private", "other": "hidden"},
        ])
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["unknown_field_count"], 2)
        self.assertNotIn("hidden", repr(result))

    def test_counts_live_profile_list_envelope_without_returning_values(self) -> None:
        result = project_site_wifi_calling_profiles_summary({"profileList": []})
        self.assertEqual(result["profile_count"], 0)
        self.assertEqual(result["carrier_count"], 0)
        self.assertFalse(result["partial"])

    def test_malformed_and_oversized_nested_values_fail_or_mark_invalid(self) -> None:
        for raw in (None, {}, [None], [{}] * 1001):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(WifiCallingProfilesError):
                project_site_wifi_calling_profiles_summary(raw)
        result = project_site_wifi_calling_profiles_summary([
            {"resource": 8, "carrierList": "bad"},
        ])
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["invalid_field_count"], 2)


class WifiCallingProfilesClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site-1"

    def test_reads_fixed_site_route_and_returns_only_summary(self) -> None:
        payload = {"result": {"profileList": [{"name": "secret", "carrierList": []}]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_site_wifi_calling_profiles_summary(SITE_REF)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-1/profiles/wifi-calling", token="token")
        self.assertEqual(result["profile_count"], 1)
        self.assertNotIn("secret", repr(result))

    def test_unknown_site_and_unsafe_route_stop_before_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_wifi_calling_profiles_summary("b" * 24)
        request.assert_not_called()
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/ctrl/sites/site-1/profiles/wifi-calling?searchKey=x")
