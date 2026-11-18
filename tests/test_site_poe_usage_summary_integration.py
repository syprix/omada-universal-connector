import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SitePoeUsageSummaryIntegrationTests(unittest.TestCase):
    def test_fixed_read_route_and_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": [{
                    "portNum": 8, "totalPowerUsed": 23, "totalPower": 120}]}) as req:
            result = client.read_site_poe_usage_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref + "/dashboard/poe-usage",
            token="token")
        self.assertEqual(result["data"]["total_power_used_watts"], 23)


if __name__ == "__main__":
    unittest.main()
