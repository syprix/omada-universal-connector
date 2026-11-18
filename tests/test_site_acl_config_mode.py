from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_acl_config_mode import (
    SiteAclConfigModeError,
    project_site_acl_config_mode,
)


class SiteAclConfigModeProjectionTests(unittest.TestCase):
    def test_projects_documented_modes(self) -> None:
        self.assertEqual(project_site_acl_config_mode({"mode": 0})["data"],
                         {"mode_code": 0, "mode_name": "through_profiles"})
        self.assertEqual(project_site_acl_config_mode({"mode": 1})["data"],
                         {"mode_code": 1, "mode_name": "custom"})

    def test_counts_missing_invalid_and_unknown_fields(self) -> None:
        missing = project_site_acl_config_mode({})
        self.assertEqual(missing["missing_field_count"], 1)
        self.assertTrue(missing["partial"])
        invalid = project_site_acl_config_mode({"mode": True, "private": "omitted"})
        self.assertEqual(invalid["invalid_field_count"], 1)
        self.assertEqual(invalid["unknown_field_count"], 1)
        self.assertNotIn("omitted", repr(invalid))

    def test_rejects_unknown_enum_values_and_invalid_shapes(self) -> None:
        for value in (2, -1, 2**31, None):
            with self.subTest(mode=value):
                self.assertEqual(project_site_acl_config_mode({"mode": value})[
                    "invalid_field_count"], 1)
        for value in (None, [], {str(i): i for i in range(9)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(
                    SiteAclConfigModeError):
                project_site_acl_config_mode(value)


class SiteAclConfigModeClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "5" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "mode": 0, "private": "omitted"}}) as request:
            result = self.client.read_site_acl_config_mode(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/acls/osg-config-mode",
            token="test-token")
        self.assertEqual(result["data"]["mode_name"], "through_profiles")
        self.assertNotIn("omitted", repr(result))

    def test_rejects_invalid_response_and_unknown_site(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_acl_config_mode(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_acl_config_mode("4" * 24)

    def test_path_guard_binds_controller(self) -> None:
        self.assertTrue(self.client._site_acl_config_mode_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/acls/osg-config-mode"))
        self.assertFalse(self.client._site_acl_config_mode_request_valid(
            "/openapi/v1/other/sites/site_internal/acls/osg-config-mode"))


if __name__ == "__main__":
    unittest.main()
