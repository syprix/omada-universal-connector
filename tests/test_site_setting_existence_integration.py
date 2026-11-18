from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_setting_existence import FIELDS


class SiteSettingExistenceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_reads_the_exact_documented_route_and_projects_all_flags(self) -> None:
        raw = {field: True for field in FIELDS}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_site_setting_existence(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/setting/exist", token="token")
        self.assertEqual(result["resource"], "site_setting_existence")
        self.assertEqual(result["data"]["settings"], {target: True for target in FIELDS.values()})
        self.assertFalse(result["partial"])

    def test_rejects_other_controller_and_preserves_invalid_flags_as_counts(self) -> None:
        good = "/openapi/v1/ctrl/sites/site_1/setting/exist"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"qos": 1}}):
            result = self.client.read_site_setting_existence(self.site_ref)
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
