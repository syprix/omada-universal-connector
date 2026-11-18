import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteSwitchDashboardSummaryIntegrationTests(unittest.TestCase):
    def test_fixed_window_and_redacted_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        fixed_now = datetime.fromtimestamp(2_000_000_000, timezone.utc)
        payload = {"clients": 4, "connectedSwitchNum": 2,
                   "portUtilization": 30, "totalTraffic": 123456}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as datetime_mock, \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            datetime_mock.now.return_value = fixed_now
            result = client.read_site_switch_dashboard_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/switch-summary?start=1999913600&end=2000000000",
            token="token")
        self.assertEqual(result["data"]["total_traffic_bytes"], 123456)

    def test_guard_requires_bound_controller_and_exact_window(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        good = "/openapi/v1/ctrl/sites/site/dashboard/switch-summary?start=10&end=86410"
        self.assertTrue(client._site_switch_dashboard_request_valid(good))
        self.assertFalse(client._site_switch_dashboard_request_valid(good.replace("/ctrl/", "/other/")))
        self.assertFalse(client._site_switch_dashboard_request_valid(good.replace("end=86410", "end=86411")))


if __name__ == "__main__":
    unittest.main()
