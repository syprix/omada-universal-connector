import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteDeviceTrafficSummaryIntegrationTests(unittest.TestCase):
    def test_fixed_trailing_day_request_and_aggregate_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {"aps": [{"name": "hidden", "traffic": 50}], "switches": []}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as clock, \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            clock.now.return_value.timestamp.return_value = 2_000_000_000
            result = client.read_site_device_traffic_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/traffic-distribution?start=1999913600&end=2000000000",
            token="token")
        self.assertEqual(result["data"]["ap_traffic_mb"], 50.0)
        self.assertNotIn("hidden", repr(result))


if __name__ == "__main__":
    unittest.main()
