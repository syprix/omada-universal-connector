import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteCurrentClientSummaryIntegrationTests(unittest.TestCase):
    def test_fixed_route_and_aggregate_counts(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "total": 21, "wiredClient": 8, "wirelessClient": 13}}) as req:
            result = client.read_site_current_client_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/current-client-num", token="token")
        self.assertEqual(result["data"]["total_client_count"], 21)
        self.assertEqual(result["data"]["wireless_client_count"], 13)


if __name__ == "__main__":
    unittest.main()
