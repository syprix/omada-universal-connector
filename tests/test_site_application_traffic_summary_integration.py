import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_application_traffic_summary import (
    SiteApplicationTrafficSummaryError,
    project_site_application_traffic_summary,
)


def sample_rows():
    return [
        {"id": 1, "name": "Private App", "familyId": 2, "familyName": "Private Family",
         "up": 20, "down": 80, "traffic": 100},
        {"id": 3, "name": "Another App", "familyId": 4, "familyName": "Other",
         "up": 5, "down": 15, "traffic": 20},
    ]


class SiteApplicationTrafficSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_projector_sums_counters_and_omits_application_labels_and_ids(self):
        result = project_site_application_traffic_summary(sample_rows())
        self.assertEqual(result["data"], {
            "returned_application_count": 2,
            "top_application_traffic_total": 120,
            "top_application_upload_total": 25,
            "top_application_download_total": 95,
        })
        self.assertFalse(result["partial"])
        for private in ("Private App", "Private Family", "Another App", "Other"):
            self.assertNotIn(private, repr(result))
        self.assertNotIn('"id"', repr(result))

    def test_projector_marks_partial_rows_and_unknown_fields(self):
        rows = sample_rows()
        rows[0]["traffic"] = True
        rows[1]["extra"] = "private-field"
        result = project_site_application_traffic_summary(rows)
        self.assertTrue(result["partial"])
        self.assertIsNone(result["data"]["top_application_traffic_total"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private-field", repr(result))

    def test_projector_validates_redacted_source_fields_too(self):
        rows = sample_rows()
        rows[0]["id"] = True
        rows[1]["familyName"] = 42
        result = project_site_application_traffic_summary(rows)
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 2)

    def test_projector_rejects_invalid_and_overbound_responses(self):
        for payload in ({}, [{}] * 11):
            with self.subTest(payload_type=type(payload).__name__), self.assertRaises(
                    SiteApplicationTrafficSummaryError):
                project_site_application_traffic_summary(payload)

    def test_read_uses_site_and_fixed_day_window(self):
        def request(method, path, token):
            self.assertEqual(method, "GET")
            self.assertTrue(self.client._site_application_traffic_request_valid(path))
            self.assertIn("/ctrl/sites/site_1/applicationControl/traffics?dateStart=", path)
            return {"result": sample_rows()}
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request) as req:
            result = self.client.read_site_application_traffic_summary("e" * 24)
        req.assert_called_once()
        self.assertEqual(result["data"]["returned_application_count"], 2)
        self.assertEqual(result["window_end_seconds"] - result["window_start_seconds"], 86_400)

    def test_outbound_guard_pins_controller_and_window(self):
        good = "/openapi/v1/ctrl/sites/site/applicationControl/traffics?dateStart=100&dateEnd=86500"
        self.assertTrue(self.client._site_application_traffic_request_valid(good))
        for bad in (good.replace("/ctrl/", "/other/"),
                    good.replace("dateEnd=86500", "dateEnd=86501"),
                    good.replace("dateStart=100", "dateStart=1&x=2")):
            self.assertFalse(self.client._site_application_traffic_request_valid(bad))

    def test_bad_upstream_shape_fails_closed(self):
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_application_traffic_summary("e" * 24)


if __name__ == "__main__":
    unittest.main()
