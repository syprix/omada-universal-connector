import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_specific_app_traffic_summary import (
    SiteSpecificAppTrafficSummaryError, project_site_specific_app_traffic_summary,
)


def sample_result():
    return [
        {"type": "Wireless", "manager": False, "clientName": "private-client-1",
         "mac": "private-mac-1", "traffic": 1000, "trafficPercent": 50.0,
         "upload": 300, "uploadTrafficPercent": 60.0, "download": 700,
         "downloadTrafficPercent": 45.0, "totalApplications": 2,
         "applicationList": [{"applicationName": "Private app"}],
         "network": "private-network", "vlanId": "private-vlan"},
        {"type": "Wired", "manager": True, "clientName": "private-client-2",
         "mac": "private-mac-2", "traffic": 500, "trafficPercent": 25.0,
         "upload": 100, "uploadTrafficPercent": 20.0, "download": 400,
         "downloadTrafficPercent": 30.0, "totalApplications": 1,
         "applicationList": [], "network": "private-network", "vlanId": "private-vlan"},
    ]


class SiteSpecificAppTrafficSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projector_aggregates_traffic_and_omits_client_details(self):
        result = project_site_specific_app_traffic_summary(sample_result())
        self.assertEqual(result["data"], {
            "client_row_count": 2, "traffic_total": 1500,
            "upload_total": 400, "download_total": 1100,
            "application_count_total": 3})
        self.assertFalse(result["partial"])
        for private in ("private-client-1", "private-mac-1", "Private app",
                        "private-network", "private-vlan"):
            self.assertNotIn(private, repr(result))

    def test_projector_marks_invalid_unknown_and_missing_fields(self):
        payload = sample_result()
        payload[0]["traffic"] = True
        payload[0]["unexpected"] = "private-value"
        del payload[1]["download"]
        result = project_site_specific_app_traffic_summary(payload)
        self.assertTrue(result["partial"])
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertGreater(result["missing_field_count"], 0)
        self.assertIsNone(result["data"]["traffic_total"])
        self.assertIsNone(result["data"]["download_total"])
        self.assertNotIn("private-value", repr(result))

    def test_projector_rejects_oversized_rows_and_malformed_root(self):
        with self.assertRaises(SiteSpecificAppTrafficSummaryError):
            project_site_specific_app_traffic_summary([{}] * 1_001)
        with self.assertRaises(SiteSpecificAppTrafficSummaryError):
            project_site_specific_app_traffic_summary({})

    def test_reads_a_safe_application_id_for_a_fixed_window(self):
        def request(_method, path, token):
            self.assertTrue(self.client._site_specific_app_info_request_valid(path))
            self.assertIn("specificAppInfo/app_123", path)
            return {"result": sample_result()}
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request) as req:
            result = self.client.read_site_specific_app_traffic_summary("e" * 24, "app_123")
        req.assert_called_once()
        self.assertEqual(result["data"]["traffic_total"], 1500)

    def test_invalid_application_id_never_reaches_upstream(self):
        with patch.object(self.client, "_resolve_site_ref") as resolve, \
                patch.object(self.client, "_request_json") as request:
            for bad in ("../escape", "id/other", "", "x" * 65):
                with self.subTest(value=bad), self.assertRaises(OpenApiError):
                    self.client.read_site_specific_app_traffic_summary("e" * 24, bad)
        resolve.assert_not_called()
        request.assert_not_called()

    def test_path_guard_pins_controller_application_and_exact_window(self):
        good = ("/openapi/v1/ctrl/sites/site/dashboard/specificAppInfo/app_123"
                "?start=100&end=86500")
        self.assertTrue(self.client._site_specific_app_info_request_valid(good))
        for bad in (good.replace("/ctrl/", "/other/"),
                    good.replace("app_123", "app/123"),
                    good.replace("end=86500", "end=86501"),
                    good + "&extra=1"):
            self.assertFalse(self.client._site_specific_app_info_request_valid(bad))

    def test_bad_upstream_shape_is_rejected(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_specific_app_traffic_summary("e" * 24, "app_123")


if __name__ == "__main__":
    unittest.main()
