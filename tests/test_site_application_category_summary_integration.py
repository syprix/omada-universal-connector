import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteApplicationCategorySummaryIntegrationTests(unittest.TestCase):
    def test_fixed_window_page_and_redacted_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        fixed_now = datetime.fromtimestamp(2_000_000_000, timezone.utc)
        payload = {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                   "data": [{"familyName": "private-category", "traffic": 90,
                             "trafficPercent": 80}],
                   "stat": {"allowApps": 2, "blockApps": 0}}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as datetime_mock, \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            datetime_mock.now.return_value = fixed_now
            result = client.read_site_application_category_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/categoryInfo?start=1999913600&end=2000000000&page=1&pageSize=100",
            token="token")
        self.assertEqual(result["data"]["maximum_category_traffic_value"], 90)
        self.assertNotIn("private-category", repr(result))

    def test_guard_binds_controller_and_exact_page_window(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        good = "/openapi/v1/ctrl/sites/site/dashboard/categoryInfo?start=10&end=86410&page=1&pageSize=100"
        self.assertTrue(client._site_application_category_request_valid(good))
        self.assertFalse(client._site_application_category_request_valid(good.replace("/ctrl/", "/other/")))
        self.assertFalse(client._site_application_category_request_valid(good.replace("end=86410", "end=86411")))
        self.assertFalse(client._site_application_category_request_valid(good.replace("pageSize=100", "pageSize=200")))


if __name__ == "__main__":
    unittest.main()
