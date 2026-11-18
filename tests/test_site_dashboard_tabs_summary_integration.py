import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_dashboard_tabs_summary import (
    SiteDashboardTabsSummaryError, project_site_dashboard_tabs_summary,
)


def sample_result():
    return [
        {"id": "private-tab-1", "name": "Private dashboard name", "type": 1,
         "cards": [1, 2, 3]},
        {"id": "private-tab-2", "name": "Other private name", "type": 1,
         "cards": [2, 4]},
        {"id": "private-tab-3", "name": "Another private name", "type": 2,
         "cards": []},
    ]


class SiteDashboardTabsSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projector_counts_types_and_cards_without_names_or_ids(self):
        result = project_site_dashboard_tabs_summary(sample_result())
        self.assertEqual(result["data"], {
            "tab_count": 3, "card_count": 5, "tab_type_counts": {"1": 2, "2": 1}})
        self.assertFalse(result["partial"])
        for private in ("private-tab-1", "Private dashboard name"):
            self.assertNotIn(private, repr(result))

    def test_projector_marks_missing_invalid_and_unknown_values(self):
        result = sample_result()
        result[0]["type"] = True
        result[0]["cards"] = [1, "private-card"]
        result[0]["extra"] = "private-extra"
        projected = project_site_dashboard_tabs_summary(result)
        self.assertTrue(projected["partial"])
        self.assertGreater(projected["invalid_field_count"], 0)
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertNotIn("private-extra", repr(projected))

    def test_projector_rejects_oversized_tab_or_card_lists(self):
        with self.assertRaises(SiteDashboardTabsSummaryError):
            project_site_dashboard_tabs_summary([{}] * 101)
        result = sample_result()
        result[0]["cards"] = [1] * 1_001
        self.assertTrue(project_site_dashboard_tabs_summary(result)["partial"])

    def test_reads_both_documented_lists_for_resolved_site(self):
        for method, route in (("read_site_dashboard_all_tabs_summary", "tabs"),
                              ("read_site_dashboard_non_overall_tabs_summary",
                               "without-overall-tabs")):
            def request(_method, path, token):
                self.assertTrue(self.client._site_dashboard_tabs_request_valid(path))
                self.assertIn(f"/dashboard/{route}", path)
                return {"result": sample_result()}
            with self.subTest(route=route), \
                    patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", side_effect=request) as req:
                result = getattr(self.client, method)("e" * 24)
            req.assert_called_once()
            self.assertEqual(result["data"]["tab_count"], 3)

    def test_path_guard_pins_controller_and_route(self):
        self.assertTrue(self.client._site_dashboard_tabs_request_valid(
            "/openapi/v1/ctrl/sites/site/dashboard/tabs"))
        self.assertTrue(self.client._site_dashboard_tabs_request_valid(
            "/openapi/v1/ctrl/sites/site/dashboard/without-overall-tabs"))
        self.assertFalse(self.client._site_dashboard_tabs_request_valid(
            "/openapi/v1/other/sites/site/dashboard/tabs"))
        self.assertFalse(self.client._site_dashboard_tabs_request_valid(
            "/openapi/v1/ctrl/sites/site/dashboard/tabs?extra=1"))

    def test_bad_upstream_shape_is_rejected(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_dashboard_all_tabs_summary("e" * 24)


if __name__ == "__main__":
    unittest.main()
