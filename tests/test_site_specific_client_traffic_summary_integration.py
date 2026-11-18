import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_specific_client_traffic_summary import (
    SiteSpecificClientTrafficSummaryError, project_site_specific_client_traffic_summary,
)

SITE_REF = "e" * 24
CLIENT_REF = "f" * 24
CLIENT_MAC = "02:00:00:00:00:01"


def sample_result():
    return [
        {"applicationName": "Private app one", "applicationId": 10,
         "applicationDescription": "private description", "familyName": "media",
         "familyId": 2, "traffic": 1_000, "trafficPercent": 80.0, "block": 0,
         "activeUser": 1, "download": 700, "upload": 300, "clientsCount": 1,
         "clients": [{"clientName": "private-client", "mac": CLIENT_MAC}]},
        {"applicationName": "Private app two", "applicationId": 11,
         "familyName": "social", "familyId": 3, "traffic": 500,
         "trafficPercent": 20.0, "block": 0, "activeUser": 1,
         "download": 400, "upload": 100, "clientsCount": 1,
         "clients": [{"clientName": "private-client", "mac": CLIENT_MAC}]},
    ]


class SiteSpecificClientTrafficSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._client_macs_by_site_ref[SITE_REF] = {CLIENT_REF: CLIENT_MAC}

    def test_projector_aggregates_traffic_without_application_or_client_details(self):
        result = project_site_specific_client_traffic_summary(sample_result())
        self.assertEqual(result["data"], {
            "application_row_count": 2, "traffic_total": 1_500,
            "download_total": 1_100, "upload_total": 400})
        self.assertFalse(result["partial"])
        for private in ("Private app one", "private description", "private-client", CLIENT_MAC):
            self.assertNotIn(private, repr(result))

    def test_projector_marks_invalid_missing_and_unknown_fields(self):
        payload = sample_result()
        payload[0]["traffic"] = True
        payload[0]["unknown"] = "private-value"
        del payload[1]["download"]
        result = project_site_specific_client_traffic_summary(payload)
        self.assertTrue(result["partial"])
        self.assertGreater(result["invalid_field_count"], 0)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertGreater(result["missing_field_count"], 0)
        self.assertIsNone(result["data"]["traffic_total"])
        self.assertIsNone(result["data"]["download_total"])
        self.assertNotIn("private-value", repr(result))

    def test_projector_rejects_oversized_or_malformed_response(self):
        with self.assertRaises(SiteSpecificClientTrafficSummaryError):
            project_site_specific_client_traffic_summary([{}] * 1_001)
        with self.assertRaises(SiteSpecificClientTrafficSummaryError):
            project_site_specific_client_traffic_summary({})

    def test_reads_only_a_fresh_inventory_client_for_the_bound_site(self):
        def request(_method, path, token):
            self.assertIn(f"specificClientInfo/{CLIENT_MAC}", path)
            self.assertTrue(self.client._site_specific_client_info_request_valid(path))
            return {"result": sample_result()}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request) as req:
            result = self.client.read_site_specific_client_traffic_summary(SITE_REF, CLIENT_REF)
        req.assert_called_once()
        self.assertEqual(result["client_ref"], CLIENT_REF)
        self.assertEqual(result["data"]["traffic_total"], 1_500)
        self.assertNotIn(CLIENT_MAC, repr(result))

    def test_unknown_client_is_rejected_before_upstream_request(self):
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaises(OpenApiError):
                self.client.read_site_specific_client_traffic_summary(SITE_REF, "a" * 24)
        request.assert_not_called()

    def test_path_guard_pins_controller_mac_and_exact_window(self):
        good = (f"/openapi/v1/ctrl/sites/site/dashboard/specificClientInfo/{CLIENT_MAC}"
                "?start=100&end=86500")
        self.assertTrue(self.client._site_specific_client_info_request_valid(good))
        for bad in (good.replace("/ctrl/", "/other/"),
                    good.replace("end=86500", "end=86501"),
                    good.replace(CLIENT_MAC, "unknown-client"),
                    good + "&extra=1"):
            self.assertFalse(self.client._site_specific_client_info_request_valid(bad))

    def test_bad_upstream_shape_is_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_specific_client_traffic_summary(SITE_REF, CLIENT_REF)


if __name__ == "__main__":
    unittest.main()
