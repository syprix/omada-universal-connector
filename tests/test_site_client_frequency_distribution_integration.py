import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteClientFrequencyDistributionIntegrationTests(unittest.TestCase):
    def test_fixed_route_and_documented_client_totals(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={
                    "result": {"total": 18, "wiredClient": 6, "wirelessClient": 12}}) as req:
            result = client.read_site_client_frequency_distribution_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/client-freq-distribution", token="token")
        self.assertEqual(result["data"]["total_client_count"], 18)
        self.assertEqual(result["data"]["wireless_client_count"], 12)


if __name__ == "__main__":
    unittest.main()
