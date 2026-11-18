from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_wids_config import (
    SiteWidsConfigError,
    project_site_wids_config,
)


class SiteWidsConfigProjectionTests(unittest.TestCase):
    def test_projects_common_fields_and_preserves_codes(self) -> None:
        result = project_site_wids_config({
            "status": True, "level": 2, "detection": [0, 15, 17],
            "unlisted": "not returned",
        })
        self.assertEqual(result["data"], {
            "enabled": True,
            "detection_level_code": 2,
            "detection_codes_applicable": True,
            "detection_codes": [0, 15, 17],
        })
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertFalse(result["partial"])
        self.assertNotIn("not returned", repr(result))

    def test_detection_is_optional_outside_custom_level(self) -> None:
        result = project_site_wids_config({"status": False, "level": 1})
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["data"]["detection_codes_applicable"], False)
        self.assertIsNone(result["data"]["detection_codes"])

    def test_missing_detection_is_partial_for_custom_level(self) -> None:
        result = project_site_wids_config({"status": True, "level": 2})
        self.assertEqual(result["missing_field_count"], 1)
        self.assertTrue(result["partial"])

    def test_invalid_fields_are_counted_without_echoing(self) -> None:
        result = project_site_wids_config({
            "status": 1, "level": 3, "detection": [True, 15],
        })
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertTrue(result["partial"])
        self.assertNotIn("True", repr(result["data"]))

    def test_rejects_invalid_outer_shapes(self) -> None:
        for value in (None, [], {str(i): i for i in range(17)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                    SiteWidsConfigError):
                project_site_wids_config(value)


class SiteWidsConfigClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "9" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_path_and_projects_response(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "status": True, "level": 0, "private": "not returned"}}) as request:
            result = self.client.read_site_wids_config(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/network-security/wireless-ids",
            token="test-token")
        self.assertEqual(result["data"]["enabled"], True)
        self.assertNotIn("not returned", repr(result))

    def test_rejects_invalid_response_and_unknown_site(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_wids_config(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_wids_config("8" * 24)

    def test_path_guard_binds_controller_and_fixed_resource(self) -> None:
        self.assertTrue(self.client._site_wids_config_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/network-security/wireless-ids"))
        self.assertFalse(self.client._site_wids_config_request_valid(
            "/openapi/v1/other/sites/site_internal/network-security/wireless-ids"))


if __name__ == "__main__":
    unittest.main()
