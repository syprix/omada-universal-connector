import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_application_access_summary import (
    SiteApplicationAccessSummaryError, project_site_application_access_summary,
)


def sample_result():
    return {
        "totalRows": 4,
        "currentPage": 1,
        "currentSize": 2,
        "data": [
            {"applicationName": "Video App", "applicationId": 8, "familyName": "Media",
             "traffic": 100, "download": 80, "upload": 20, "activeUser": 3,
             "clientsCount": 4, "clients": [{"clientName": "private-user",
                                               "mac": "private-mac"}]},
            {"applicationName": "Chat App", "applicationId": 9, "familyName": "Social",
             "traffic": 50, "download": 40, "upload": 10, "activeUser": 2,
             "clientsCount": 2, "clients": [{"clientName": "private-user"}]},
        ],
        "stat": {"allowApps": 14, "blockApps": 3},
    }


class SiteApplicationAccessSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projector_sums_counters_and_omits_app_and_client_details(self):
        result = project_site_application_access_summary(sample_result())
        data = result["data"]
        self.assertEqual(data["returned_application_count"], 2)
        self.assertEqual(data["page_traffic_total"], 150)
        self.assertEqual(data["page_download_total"], 120)
        self.assertEqual(data["page_upload_total"], 30)
        self.assertEqual(data["page_active_user_total"], 5)
        self.assertEqual(data["page_client_count_total"], 6)
        self.assertEqual(data["has_more_pages"], True)
        self.assertFalse(result["partial"])
        for private in ("Video App", "private-user", "private-mac"):
            self.assertNotIn(private, repr(result))

    def test_projector_marks_partial_numeric_rows_and_unknown_fields(self):
        payload = sample_result()
        payload["data"][0]["traffic"] = True
        payload["data"][0]["unknown"] = "private-value"
        result = project_site_application_access_summary(payload)
        self.assertTrue(result["partial"])
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertIsNone(result["data"]["page_traffic_total"])
        self.assertNotIn("private-value", repr(result))

    def test_projector_rejects_over_bound_page(self):
        payload = sample_result()
        payload["data"] = [{}] * 101
        with self.assertRaises(SiteApplicationAccessSummaryError):
            project_site_application_access_summary(payload)
        with self.assertRaises(SiteApplicationAccessSummaryError):
            project_site_application_access_summary([])

    def test_continuation_uses_requested_page_size(self):
        payload = sample_result()
        self.assertFalse(project_site_application_access_summary(
            payload, page_size=10)["data"]["has_more_pages"])

    def test_allowed_and_blocked_reads_bind_site_and_page(self):
        for method, route in (("read_site_allowed_application_summary", "allowApp"),
                              ("read_site_blocked_application_summary", "blockApp")):
            def request(_method, path, token):
                self.assertTrue(self.client._site_application_access_request_valid(path))
                self.assertIn(f"/dashboard/{route}?", path)
                self.assertIn("page=4&pageSize=2", path)
                return {"result": sample_result()}
            with self.subTest(route=route), \
                    patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", side_effect=request) as req:
                result = getattr(self.client, method)("e" * 24, 3, 2)
            req.assert_called_once()
            self.assertEqual(result["page_number"], 3)
            self.assertEqual(result["page_size"], 2)

    def test_path_guard_pins_controller_window_and_bounded_pagination(self):
        good = ("/openapi/v1/ctrl/sites/site/dashboard/allowApp"
                "?start=100&end=86500&page=1&pageSize=100")
        self.assertTrue(self.client._site_application_access_request_valid(good))
        for bad in (good.replace("/ctrl/", "/other/"),
                    good.replace("end=86500", "end=86501"),
                    good.replace("pageSize=100", "pageSize=1000"),
                    good.replace("page=1", "page=0"),
                    good.replace("allowApp", "other")):
            self.assertFalse(self.client._site_application_access_request_valid(bad))

    def test_bad_page_and_bad_upstream_shape_fail_closed(self):
        with self.assertRaises(OpenApiError):
            self.client.read_site_allowed_application_summary("e" * 24, 0, 101)
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_blocked_application_summary("e" * 24, 0, 10)


if __name__ == "__main__":
    unittest.main()
