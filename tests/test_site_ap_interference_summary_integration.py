import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteApInterferenceSummaryIntegrationTests(unittest.TestCase):
    def test_fixed_route_and_redacted_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {"apInterference2g": [{"name": "private-ap", "interUtil": 55}],
                   "apInterference5g": [], "apInterference5g2": [],
                   "apInterference6g": []}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            result = client.read_site_ap_interference_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/top-interference", token="token")
        self.assertEqual(result["data"]["2g_maximum_interference_value"], 55)
        self.assertNotIn("private-ap", repr(result))

    def test_guard_binds_controller(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        good = "/openapi/v1/ctrl/sites/site/dashboard/top-interference"
        self.assertTrue(client._site_ap_interference_request_valid(good))
        self.assertFalse(client._site_ap_interference_request_valid(good.replace("/ctrl/", "/other/")))


if __name__ == "__main__":
    unittest.main()
