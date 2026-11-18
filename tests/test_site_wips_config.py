from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wips_config import SiteWipsConfigError, project_site_wips_config


class SiteWipsConfigProjectionTests(unittest.TestCase):
    def test_projects_documented_fields_and_lock_time(self) -> None:
        result = project_site_wips_config({
            "status": True, "deauthEn": False, "dynamicEn": True,
            "lockTime": 300,
        })
        self.assertEqual(result["data"], {
            "enabled": True, "deauthentication_enabled": False,
            "dynamic_blocking_enabled": True, "lock_time_seconds": 300,
        })
        self.assertFalse(result["partial"])

    def test_requires_lock_time_when_dynamic_blocking_is_enabled(self) -> None:
        result = project_site_wips_config({
            "status": True, "deauthEn": True, "dynamicEn": True,
        })
        self.assertEqual(result["missing_field_count"], 1)
        self.assertTrue(result["partial"])

    def test_allows_omitted_lock_time_when_dynamic_blocking_is_disabled(self) -> None:
        result = project_site_wips_config({
            "status": True, "deauthEn": False, "dynamicEn": False,
        })
        self.assertEqual(result["missing_field_count"], 0)
        self.assertFalse(result["partial"])

    def test_rejects_invalid_types_and_lock_time_range(self) -> None:
        for value in (True, False, 299, 36_001, 2**31):
            with self.subTest(lockTime=value):
                result = project_site_wips_config({
                    "status": True, "deauthEn": True, "dynamicEn": True,
                    "lockTime": value,
                })
                self.assertEqual(result["invalid_field_count"], 1)
                self.assertIsNone(result["data"]["lock_time_seconds"])

    def test_counts_unknown_and_invalid_boolean_fields_without_echoing(self) -> None:
        result = project_site_wips_config({
            "status": "enabled", "deauthEn": False, "dynamicEn": False,
            "private": "not returned",
        })
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("not returned", repr(result))

    def test_rejects_invalid_outer_shapes(self) -> None:
        for value in (None, [], {str(i): i for i in range(13)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                    SiteWipsConfigError):
                project_site_wips_config(value)


class SiteWipsConfigClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "7" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "status": True, "deauthEn": False, "dynamicEn": False}}) as request:
            result = self.client.read_site_wips_config(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/network-security/wireless-ips",
            token="test-token")
        self.assertEqual(result["data"]["enabled"], True)

    def test_rejects_invalid_response_and_unknown_site(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_wips_config(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_wips_config("6" * 24)

    def test_path_guard_binds_controller(self) -> None:
        self.assertTrue(self.client._site_wips_config_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/network-security/wireless-ips"))
        self.assertFalse(self.client._site_wips_config_request_valid(
            "/openapi/v1/other/sites/site_internal/network-security/wireless-ips"))


if __name__ == "__main__":
    unittest.main()
