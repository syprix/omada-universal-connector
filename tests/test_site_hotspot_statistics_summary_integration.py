import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_hotspot_statistics_summary import (
    SiteHotspotStatisticsSummaryError, project_site_hotspot_statistics_summary,
)


def sample_result():
    return {
        "lastConnection": [
            {"newNum": 2, "existingNum": 5, "startTime": 1000, "endTime": 2000},
            {"newNum": 3, "existingNum": 6, "startTime": 3000, "endTime": 4000},
        ],
        "authTypeDistribution": {"noAuth": 1, "simplePassword": 2, "hotspot": 3,
            "facebook": 0, "externalRadius": 1, "externalPortal": 0, "ldap": 0,
            "google": 0},
        "hotspotDistribution": {"total": 4, "voucher": 2, "localUser": 1,
            "sms": 0, "form": 1, "hotspotRadius": 0},
    }


class SiteHotspotStatisticsSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projector_aggregates_auth_and_hotspot_distributions(self):
        result = project_site_hotspot_statistics_summary(sample_result())
        data = result["data"]
        self.assertEqual(data["last_connection_sample_count"], 2)
        self.assertEqual(data["total_new_authenticated_clients"], 5)
        self.assertEqual(data["total_existing_authenticated_clients"], 11)
        self.assertEqual(data["earliest_source_time"], 1000)
        self.assertEqual(data["latest_source_time"], 4000)
        self.assertEqual(data["authentication_type_counts"]["hotspot"], 3)
        self.assertEqual(data["hotspot_type_counts"]["voucher"], 2)
        self.assertFalse(result["partial"])

    def test_projector_omits_unknown_fields_and_marks_result_partial(self):
        value = sample_result()
        value["privateName"] = "private-hotspot-user"
        projected = project_site_hotspot_statistics_summary(value)
        self.assertTrue(projected["partial"])
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertNotIn("private-hotspot-user", repr(projected))

    def test_projector_marks_invalid_or_missing_distribution_fields(self):
        value = sample_result()
        value["authTypeDistribution"]["noAuth"] = True
        del value["hotspotDistribution"]["voucher"]
        projected = project_site_hotspot_statistics_summary(value)
        self.assertTrue(projected["partial"])
        self.assertGreater(projected["invalid_field_count"], 0)
        self.assertGreater(projected["missing_field_count"], 0)

    def test_projector_rejects_nonobject_and_oversized_samples(self):
        with self.assertRaises(SiteHotspotStatisticsSummaryError):
            project_site_hotspot_statistics_summary([])
        value = sample_result()
        value["lastConnection"] = [{}] * 2_001
        with self.assertRaises(SiteHotspotStatisticsSummaryError):
            project_site_hotspot_statistics_summary(value)

    def test_reads_fixed_24_hour_window_for_bound_site(self):
        site_ref = "e" * 24
        def request(_method, path, token):
            self.assertTrue(self.client._site_hotspot_statistics_request_valid(path))
            return {"result": sample_result()}
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request) as req:
            result = self.client.read_site_hotspot_statistics_summary(site_ref)
        req.assert_called_once()
        self.assertEqual(result["data"]["total_new_authenticated_clients"], 5)
        self.assertEqual(result["site_ref"], site_ref)

    def test_path_guard_binds_controller_and_fixed_window(self):
        good = ("/openapi/v1/ctrl/sites/site/hotspot/dashboard/statistics"
                "?start=100&end=86500")
        self.assertTrue(self.client._site_hotspot_statistics_request_valid(good))
        self.assertFalse(self.client._site_hotspot_statistics_request_valid(
            good.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_hotspot_statistics_request_valid(
            good.replace("end=86500", "end=86501")))

    def test_bad_upstream_shape_is_rejected(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_hotspot_statistics_summary("e" * 24)


if __name__ == "__main__":
    unittest.main()
