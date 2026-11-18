import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteNetworkActivitySummaryIntegrationTests(unittest.TestCase):
    def test_fixed_trailing_day_route_and_redacted_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {"totalTraffic": 900, "totalUpload": 300,
                   "totalDownload": 600, "existData": True,
                   "totalWiredCount": 2, "totalWirelessCount": 4,
                   "totalClientCount": 6,
                   "activityList": [{"clientName": "must-not-leak"}]}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as clock, \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            clock.now.return_value.timestamp.return_value = 2_000_000_000
            result = client.read_site_network_activity_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/allNetworkActivity?start=1999913600&end=2000000000",
            token="token")
        self.assertEqual(result["window_start_seconds"], 1_999_913_600)
        self.assertEqual(result["data"]["total_download_traffic"], 600)
        self.assertNotIn("must-not-leak", repr(result))


if __name__ == "__main__":
    unittest.main()
