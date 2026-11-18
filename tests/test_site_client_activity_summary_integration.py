import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_client_activity_summary import (
    SiteClientActivitySummaryError, project_site_client_activity_summary,
)


class SiteClientActivitySummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projector_summarizes_counts_and_discards_identity_fields(self):
        result = project_site_client_activity_summary([
            {"time": 100, "newEapClientNum": 2, "newSwitchClientNum": 1,
             "activeEapClientNum": 9, "activeSwitchClientNum": 3,
             "disconnectEapClientNum": 1, "disconnectSwitchClientNum": 0,
             "clientName": "private-client"},
            {"time": 200, "newEapClientNum": 1, "newSwitchClientNum": 0,
             "activeEapClientNum": 7, "activeSwitchClientNum": 2,
             "disconnectEapClientNum": 0, "disconnectSwitchClientNum": 1},
        ])
        data = result["data"]
        self.assertEqual(data["sample_count"], 2)
        self.assertEqual(data["first_sample_time"], 100)
        self.assertEqual(data["last_sample_time"], 200)
        self.assertEqual(data["total_new_eap_clients"], 3)
        self.assertEqual(data["total_new_switch_clients"], 1)
        self.assertEqual(data["mean_active_eap_clients_per_sample"], 8)
        self.assertEqual(data["peak_active_switch_clients_per_sample"], 3)
        self.assertEqual(data["total_disconnected_eap_clients"], 1)
        self.assertEqual(data["total_disconnected_switch_clients"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private-client", repr(result))

    def test_projector_marks_invalid_and_missing_counts_partial(self):
        projected = project_site_client_activity_summary([{
            "time": 100, "newEapClientNum": -1,
        }])
        self.assertTrue(projected["partial"])
        self.assertIsNone(projected["data"]["total_new_eap_clients"])
        self.assertGreater(projected["invalid_field_count"], 0)
        self.assertGreater(projected["missing_field_count"], 0)

    def test_projector_rejects_nonlist_and_oversized_results(self):
        with self.assertRaises(SiteClientActivitySummaryError):
            project_site_client_activity_summary({})
        with self.assertRaises(SiteClientActivitySummaryError):
            project_site_client_activity_summary([{}] * 2_001)

    def test_reads_fixed_24_hour_window_for_bound_site(self):
        site_ref = "a" * 24
        payload = [{"time": 100, "newEapClientNum": 2, "newSwitchClientNum": 1,
                    "activeEapClientNum": 9, "activeSwitchClientNum": 3,
                    "disconnectEapClientNum": 1, "disconnectSwitchClientNum": 0}]
        def request(_method, path, token):
            self.assertTrue(self.client._site_client_activity_request_valid(path))
            return {"result": payload}
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request) as req:
            result = self.client.read_site_client_activity_summary(site_ref)
        req.assert_called_once()
        self.assertEqual(result["data"]["total_new_eap_clients"], 2)
        self.assertEqual(result["site_ref"], site_ref)

    def test_path_guard_binds_controller_and_fixed_window(self):
        good = ("/openapi/v1/ctrl/sites/site/dashboard/client-activity"
                "?start=100&end=86500")
        self.assertTrue(self.client._site_client_activity_request_valid(good))
        self.assertFalse(self.client._site_client_activity_request_valid(
            good.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_client_activity_request_valid(
            good.replace("end=86500", "end=86501")))

    def test_bad_upstream_result_is_rejected(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_client_activity_summary("a" * 24)


if __name__ == "__main__":
    unittest.main()
