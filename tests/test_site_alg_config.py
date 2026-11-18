from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_alg_config import SiteAlgConfigError, project_site_alg_config


class SiteAlgConfigProjectionTests(unittest.TestCase):
    def test_projects_all_common_typed_fields(self) -> None:
        source = {
            "ftp": True, "h323": True, "pptp": False, "sip": True,
            "ipSec": False, "ftpPorts": [21], "sipTcp": True,
            "sipUdp": False, "sipPorts": [5060, 5061],
            "sipDirectSignaling": False, "sipDirectMedia": True,
            "sipTimeout": True, "sipSignalingTimeout": 86_400,
            "sipMediaTimeout": 1, "supportSipAlgConfig": True,
            "existSipAlgConfig": False, "existFtpAlgConfig": True,
        }
        result = project_site_alg_config(source)
        self.assertEqual(result["data"], source)
        self.assertEqual(result["missing_field_count"], 0)
        self.assertFalse(result["partial"])

    def test_missing_required_fields_are_reported(self) -> None:
        result = project_site_alg_config({"ftp": True})
        self.assertEqual(result["missing_field_count"], 4)
        self.assertTrue(result["partial"])

    def test_invalid_booleans_arrays_and_timeouts_are_counted(self) -> None:
        result = project_site_alg_config({
            "ftp": 1, "h323": True, "ipSec": False, "pptp": True, "sip": True,
            "ftpPorts": [21, True], "sipSignalingTimeout": 86_401,
        })
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertTrue(result["partial"])

    def test_unknown_fields_are_omitted(self) -> None:
        result = project_site_alg_config({"ftp": True, "private": "not returned"})
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("not returned", repr(result))

    def test_rejects_invalid_outer_shapes(self) -> None:
        for value in (None, [], {str(i): i for i in range(33)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(
                    SiteAlgConfigError):
                project_site_alg_config(value)


class SiteAlgConfigClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "1" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "ftp": True, "h323": False, "ipSec": True,
                    "pptp": False, "sip": True,
                }}) as request:
            result = self.client.read_site_alg_config(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/nat/alg",
            token="test-token")
        self.assertEqual(result["data"]["ftp"], True)

    def test_rejects_invalid_response_and_unknown_site(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_alg_config(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_alg_config("0" * 24)

    def test_path_guard_binds_controller(self) -> None:
        self.assertTrue(self.client._site_alg_config_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/nat/alg"))
        self.assertFalse(self.client._site_alg_config_request_valid(
            "/openapi/v1/other/sites/site_internal/nat/alg"))


if __name__ == "__main__":
    unittest.main()
