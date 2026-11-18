import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_active_ap_v2_summary import (
    SiteActiveApV2SummaryError, project_site_active_ap_v2_summary,
)


class SiteActiveApV2SummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projector_aggregates_top_ten_and_discards_device_identity(self):
        result = project_site_active_ap_v2_summary({
            "totalTraffic": 180.5,
            "activeAps": [
                {"status": 0, "name": "private-ap-one", "traffic": 100.25,
                 "mac": "aa:bb", "model": "private-model", "modelVersion": "1"},
                {"status": 1, "name": "private-ap-two", "traffic": 80.25,
                 "mac": "cc:dd", "model": "private-model", "modelVersion": "1"},
            ],
        })
        self.assertEqual(result["data"]["active_ap_count"], 2)
        self.assertEqual(result["data"]["connected_ap_count"], 1)
        self.assertEqual(result["data"]["disconnected_ap_count"], 1)
        self.assertEqual(result["data"]["reported_total_traffic_value"], 180.5)
        self.assertEqual(result["data"]["maximum_ap_traffic_gb"], 100.25)
        self.assertFalse(result["partial"])
        for private in ("private-ap-one", "aa:bb", "private-model"):
            self.assertNotIn(private, repr(result))

    def test_projector_marks_invalid_reported_total_partial(self):
        result = project_site_active_ap_v2_summary({"activeAps": [], "totalTraffic": {"value": 3}})
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertIsNone(result["data"]["reported_total_traffic_value"])

    def test_projector_rejects_bad_shape_and_more_than_ten_aps(self):
        with self.assertRaises(SiteActiveApV2SummaryError):
            project_site_active_ap_v2_summary([])
        with self.assertRaises(SiteActiveApV2SummaryError):
            project_site_active_ap_v2_summary({"activeAps": [{}] * 11,
                                               "totalTraffic": 1})

    def test_reads_fixed_window_and_device_num_ten_for_bound_site(self):
        site_ref = "d" * 24
        def request(_method, path, token):
            self.assertTrue(self.client._site_active_ap_v2_request_valid(path))
            self.assertIn("?deviceNum=10&start=", path)
            return {"result": {"totalTraffic": 10.0, "activeAps": [
                {"status": 0, "traffic": 10.0}]}}
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request) as req:
            result = self.client.read_site_active_ap_v2_summary(site_ref)
        req.assert_called_once()
        self.assertEqual(result["data"]["active_ap_count"], 1)
        self.assertEqual(result["site_ref"], site_ref)

    def test_path_guard_binds_v2_controller_device_num_and_window(self):
        good = ("/openapi/v2/ctrl/sites/site/dashboard/most-active-eaps"
                "?deviceNum=10&start=100&end=86500")
        self.assertTrue(self.client._site_active_ap_v2_request_valid(good))
        self.assertFalse(self.client._site_active_ap_v2_request_valid(
            good.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_active_ap_v2_request_valid(
            good.replace("deviceNum=10", "deviceNum=100")))
        self.assertFalse(self.client._site_active_ap_v2_request_valid(
            good.replace("end=86500", "end=86501")))

    def test_bad_upstream_shape_is_rejected(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_active_ap_v2_summary("d" * 24)


if __name__ == "__main__":
    unittest.main()
