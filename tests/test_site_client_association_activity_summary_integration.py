import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_client_association_activity_summary import (
    SiteClientAssociationActivitySummaryError,
    project_site_client_association_activity_summary,
)


class SiteClientAssociationActivitySummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projector_returns_only_valid_aggregate_counts(self):
        projected = project_site_client_association_activity_summary({
            "total": 12, "wiredClient": 3, "wirelessClient": 9,
            "privateIdentity": "omitted",
        })
        self.assertEqual(projected["data"], {
            "total_clients": 12, "wired_clients": 3, "wireless_clients": 9,
        })
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertNotIn("omitted", repr(projected))

    def test_projector_marks_invalid_or_missing_values_partial(self):
        projected = project_site_client_association_activity_summary({
            "total": True, "wiredClient": -1,
        })
        self.assertTrue(projected["partial"])
        self.assertEqual(projected["data"], {})
        self.assertEqual(projected["missing_field_count"], 1)
        self.assertEqual(projected["invalid_field_count"], 2)

    def test_projector_rejects_nonobject_and_oversized_results(self):
        with self.assertRaises(SiteClientAssociationActivitySummaryError):
            project_site_client_association_activity_summary([])
        with self.assertRaises(SiteClientAssociationActivitySummaryError):
            project_site_client_association_activity_summary({str(i): i for i in range(9)})

    def test_reads_fixed_24_hour_interval_for_bound_site(self):
        site_ref = "b" * 24
        def request(_method, path, token):
            self.assertTrue(self.client._site_client_association_activity_request_valid(path))
            return {"result": {"total": 12, "wiredClient": 3, "wirelessClient": 9}}
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request) as req:
            result = self.client.read_site_client_association_activity_summary(site_ref)
        req.assert_called_once()
        self.assertEqual(result["data"]["total_clients"], 12)
        self.assertEqual(result["site_ref"], site_ref)

    def test_path_guard_binds_controller_and_fixed_window(self):
        good = ("/openapi/v1/ctrl/sites/site/dashboard/client-association-activities"
                "?start=100&end=86500")
        self.assertTrue(self.client._site_client_association_activity_request_valid(good))
        self.assertFalse(self.client._site_client_association_activity_request_valid(
            good.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_client_association_activity_request_valid(
            good.replace("end=86500", "end=86501")))

    def test_bad_upstream_result_is_rejected(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_client_association_activity_summary("b" * 24)


if __name__ == "__main__":
    unittest.main()
