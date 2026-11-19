from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.site_wan_max_speed_summary import (
    SiteWanMaxSpeedError, project_site_wan_max_speed,
)


class SiteWanMaxSpeedProjectionTests(unittest.TestCase):
    def test_preserves_documented_int32_values_and_unknown_unit(self) -> None:
        result = project_site_wan_max_speed({"upstream": 0, "downstream": 125000})
        self.assertEqual(result["data"], {
            "upstream": 0, "downstream": 125000, "unit": "unspecified_by_source"})
        self.assertFalse(result["partial"])

    def test_missing_invalid_and_unknown_fields_are_counted(self) -> None:
        result = project_site_wan_max_speed({
            "upstream": True, "downstream": -(2 ** 31) - 1, "extra": "private"})
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private", repr(result))

    def test_missing_fields_are_partial_and_bad_outer_shapes_rejected(self) -> None:
        result = project_site_wan_max_speed({"upstream": 42})
        self.assertEqual(result["missing_field_count"], 1)
        self.assertIsNone(result["data"]["downstream"])
        for value in (None, [], {str(i): i for i in range(17)}):
            with self.subTest(value=type(value).__name__), \
                    self.assertRaises(SiteWanMaxSpeedError):
                project_site_wan_max_speed(value)


class SiteWanMaxSpeedClientTests(unittest.TestCase):
    def test_uses_fixed_site_read_and_projects_response(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        site_ref = "8" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={
                    "result": {"upstream": 5, "downstream": 8}}) as request:
            result = client.read_site_wan_max_speed_summary(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/wan-max-speed", token="token")
        self.assertEqual(result["data"]["upstream"], 5)
        self.assertEqual(result["data"]["unit"], "unspecified_by_source")


if __name__ == "__main__":
    unittest.main()
