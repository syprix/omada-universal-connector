import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SitePastClientSummaryIntegrationTests(unittest.TestCase):
    def test_fixed_trailing_day_and_aggregate_counts(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as clock, \
                patch.object(client, "_request_json", return_value={"result": {
                    "total": 32, "wiredClient": 9, "wirelessClient": 23}}) as req:
            clock.now.return_value.timestamp.return_value = 2_000_000_000
            result = client.read_site_past_client_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/past-client-num?start=1999913600&end=2000000000",
            token="token")
        self.assertEqual(result["window_start_seconds"], 1_999_913_600)
        self.assertEqual(result["data"]["wireless_client_count"], 23)


if __name__ == "__main__":
    unittest.main()
