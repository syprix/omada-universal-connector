from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_disaster_mode_status import (
    SiteDisasterModeStatusError,
    project_site_disaster_mode_status,
)


class SiteDisasterModeProjectionTests(unittest.TestCase):
    def test_projects_documented_int32_code_without_interpreting_it(self) -> None:
        result = project_site_disaster_mode_status({"status": 2})
        self.assertEqual(result["data"], {"status_code": 2})
        self.assertFalse(result["partial"])

    def test_counts_missing_invalid_unknown_without_echoing_values(self) -> None:
        result = project_site_disaster_mode_status({
            "status": True, "privateSetting": "do-not-return",
        })
        self.assertEqual(result["data"], {"status_code": None})
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("do-not-return", repr(result))

    def test_rejects_invalid_shapes_and_out_of_range_codes(self) -> None:
        for value in (None, [], {str(i): i for i in range(9)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(
                    SiteDisasterModeStatusError):
                project_site_disaster_mode_status(value)
        out_of_range = project_site_disaster_mode_status({"status": 2**31})
        self.assertEqual(out_of_range["data"]["status_code"], None)
        self.assertEqual(out_of_range["invalid_field_count"], 1)


class SiteDisasterModeClientTests(unittest.TestCase):
    def test_uses_inventory_bound_site_and_fixed_controller_path(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref = "c" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "status": 1, "privateField": "no-echo",
                }}) as request:
            result = client.read_site_disaster_mode_status(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/setting/disaster",
            token="test-token")
        self.assertEqual(result["resource"], "site_disaster_mode_status")
        self.assertEqual(result["data"]["status_code"], 1)
        self.assertNotIn("no-echo", repr(result))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            client.read_site_disaster_mode_status("d" * 24)

    def test_path_guard_requires_the_configured_controller(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.assertTrue(client._site_disaster_mode_status_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/setting/disaster"))
        self.assertFalse(client._site_disaster_mode_status_request_valid(
            "/openapi/v1/other/sites/site_internal/setting/disaster"))


if __name__ == "__main__":
    unittest.main()
