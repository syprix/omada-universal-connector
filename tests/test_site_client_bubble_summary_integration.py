import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteClientBubbleSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_reads_exact_fixed_route_and_redacts_client_identifiers(self):
        site_ref = "a" * 24
        payload = [{"name": "hidden-client", "mac": "02:00:00:00:00:01",
                    "apName": "private-ap", "traffic": 90, "upload": 30,
                    "download": 60, "rssi": -50, "snr": 40, "healthScore": 90}]
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as req:
            result = self.client.read_site_client_bubble_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/dashboard/clients-bubble", token="token")
        self.assertEqual(result["data"]["client_count"], 1)
        self.assertNotIn("hidden-client", repr(result))
        self.assertNotIn("private-ap", repr(result))

    def test_path_guard_binds_controller_and_rejects_query(self):
        good = "/openapi/v1/ctrl/sites/site/dashboard/clients-bubble"
        self.assertTrue(self.client._site_client_bubble_request_valid(good))
        self.assertFalse(self.client._site_client_bubble_request_valid(
            good.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_client_bubble_request_valid(good + "?page=1"))


if __name__ == "__main__":
    unittest.main()
