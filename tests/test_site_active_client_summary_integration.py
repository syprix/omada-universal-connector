import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteActiveClientSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_reads_exact_site_route_and_projects_redacted_counts(self):
        site_ref = "a" * 24
        payload = [{"name": "hidden-client", "wireless": True,
                    "mac": "02:00:00:00:00:01", "totalTraffic": 90}]
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as req:
            result = self.client.read_site_active_client_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/dashboard/active-clients", token="token")
        self.assertEqual(result["data"]["wireless_client_count"], 1)
        self.assertNotIn("hidden-client", repr(result))

    def test_path_guard_binds_controller_and_rejects_query(self):
        good = "/openapi/v1/ctrl/sites/site/dashboard/active-clients"
        self.assertTrue(self.client._site_active_client_request_valid(good))
        self.assertFalse(self.client._site_active_client_request_valid(
            good.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_active_client_request_valid(good + "?page=2"))


if __name__ == "__main__":
    unittest.main()
