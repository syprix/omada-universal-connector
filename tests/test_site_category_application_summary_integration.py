import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SiteCategoryApplicationSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_window_route_and_redacted_projection(self):
        site_ref, family_id = "a" * 24, "17"
        fixed_now = datetime.fromtimestamp(2_000_000_000, timezone.utc)
        payload = [{"applicationName": "hidden-app", "applicationId": 7,
                    "traffic": 60, "trafficPercent": 80, "block": 2,
                    "activeUser": 3, "upload": 10, "download": 50,
                    "clientsCount": 4, "clients": []}]
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as datetime_mock, \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as req:
            datetime_mock.now.return_value = fixed_now
            result = self.client.read_site_category_application_summary(site_ref, family_id)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/dashboard/categoryAppInfo/17"
            "?start=1999913600&end=2000000000", token="token")
        self.assertEqual(result["data"]["application_count"], 1)
        self.assertNotIn("hidden-app", repr(result))

    def test_path_guard_binds_controller_family_and_window(self):
        good = "/openapi/v1/ctrl/sites/site/dashboard/categoryAppInfo/17?start=10&end=86410"
        self.assertTrue(self.client._site_category_application_request_valid(good))
        self.assertFalse(self.client._site_category_application_request_valid(
            good.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_category_application_request_valid(
            good.replace("/17?", "/2147483648?")))
        self.assertFalse(self.client._site_category_application_request_valid(
            good.replace("end=86410", "end=86411")))

    def test_rejects_family_ids_outside_documented_numeric_domain(self):
        with self.assertRaisesRegex(OpenApiError, "category_id_invalid"):
            self.client.read_site_category_application_summary("a" * 24, "17/../x")
        with self.assertRaisesRegex(OpenApiError, "category_id_invalid"):
            self.client.read_site_category_application_summary("a" * 24, "2147483648")


if __name__ == "__main__":
    unittest.main()
