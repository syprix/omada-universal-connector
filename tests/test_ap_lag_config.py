from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_lag import ApLagError, project_ap_lag
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ApLagConfigProjectionTests(unittest.TestCase):
    def test_projects_documented_values_and_omits_unknown_values(self):
        result = project_ap_lag({
            "supportTrunkSetting": True, "enable": False, "mode": 2,
            "unknown": "private-value",
        })
        self.assertEqual(result["resource"], "ap_lag")
        self.assertEqual(result["data"], {
            "supportTrunkSetting": True, "enable": False, "mode": 2,
        })
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private-value", repr(result))

    def test_rejects_invalid_root(self):
        with self.assertRaises(ApLagError):
            project_ap_lag([])


class ApLagConfigClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref, self.ap_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"
        self.client._device_macs_by_site_ref[self.site_ref] = {
            self.ap_ref: "AA-BB-CC-DD-EE-FF"}

    def test_reads_the_distinct_fixed_lag_route(self):
        response = {"errorCode": 0, "result": {
            "supportTrunkSetting": True, "enable": True, "mode": 1}}
        path = "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/lag"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=response) as request:
            result = self.client.read_ap_lag_config(self.site_ref, self.ap_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["resource"], "ap_lag_config")
        self.assertEqual(result["data"]["mode"], 1)

    def test_rejects_modified_path_before_network_io(self):
        with patch.object(self.client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET",
                    "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/lag?path=/evil")
        connection.assert_not_called()

    def test_rejects_nonzero_controller_error(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"errorCode": 1}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_ap_lag_config(self.site_ref, self.ap_ref)


if __name__ == "__main__":
    unittest.main()
