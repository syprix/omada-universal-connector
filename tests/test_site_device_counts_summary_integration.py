import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteDeviceCountsSummaryIntegrationTests(unittest.TestCase):
    def test_fixed_read_route_and_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = [{"type": "ap", "total": 2, "preConfig": 0,
                    "connected": 2, "disconnectedCount": 0}]
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            result = client.read_site_device_counts_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref + "/dashboard/card/overview",
            token="token")
        self.assertEqual(result["data"]["total_device_count"], 2)


if __name__ == "__main__":
    unittest.main()
