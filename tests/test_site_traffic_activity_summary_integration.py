import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteTrafficActivitySummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_reads_exact_24_hour_route_and_projects_result(self):
        site_ref = "a" * 24
        fixed_now = datetime.fromtimestamp(2_000_000_000, timezone.utc)
        payload = {"apTrafficActivities": [
            {"time": 2_000_000_000, "txData": 4.0, "rxData": 8.0}],
            "switchTrafficActivities": []}
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as datetime_mock, \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as req:
            datetime_mock.now.return_value = fixed_now
            result = self.client.read_site_traffic_activity_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/dashboard/traffic-activities"
            "?start=1999913600&end=2000000000", token="token")
        self.assertEqual(result["data"]["access_point_traffic"]["sample_count"], 1)

    def test_path_guard_binds_controller_and_exact_window(self):
        good = ("/openapi/v1/ctrl/sites/site/dashboard/traffic-activities"
                "?start=10&end=86410")
        self.assertTrue(self.client._site_traffic_activity_request_valid(good))
        self.assertFalse(self.client._site_traffic_activity_request_valid(
            good.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_traffic_activity_request_valid(
            good.replace("end=86410", "end=86411")))


if __name__ == "__main__":
    unittest.main()
