from __future__ import annotations

import unittest
from datetime import datetime as RealDateTime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_incident_category_counts import (
    COUNT_FIELDS, MAX_CATEGORIES, MAX_INT32, SiteIncidentCategoryCountsError,
    project_site_incident_category_counts,
)


SITE = "a" * 24
NOW_MS = 1_800_000_000_000


class SiteIncidentCategoryCountsTests(unittest.TestCase):
    def test_projects_bounded_category_aggregates(self) -> None:
        row = {name: i for i, name in enumerate(COUNT_FIELDS, start=1)}
        row["anomalyCode"] = "01001001"
        row["level"] = 2
        result = project_site_incident_category_counts([row])
        self.assertEqual(result["data"]["category_count"], 1)
        category = result["data"]["categories"][0]
        self.assertEqual(category["anomaly_code"], "01001001")
        self.assertEqual(category["counts"]["active_count"], 1)
        self.assertFalse(result["partial"])

    def test_redacts_unknown_values_and_marks_incomplete_rows(self) -> None:
        result = project_site_incident_category_counts([{
            "anomalyCode": "private code",
            "counts": True,
            "deviceName": "private device",
        }])
        category = result["data"]["categories"][0]
        self.assertIsNone(category["anomaly_code"])
        self.assertEqual(result["data"]["invalid_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertGreater(result["data"]["missing_count"], 0)
        self.assertNotIn("private device", repr(result))
        self.assertTrue(result["partial"])

    def test_rejects_bad_envelopes_and_oversized_lists(self) -> None:
        for value in (None, {}, [None] * (MAX_CATEGORIES + 1)):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                    SiteIncidentCategoryCountsError):
                project_site_incident_category_counts(value)
        self.assertEqual(project_site_incident_category_counts([])["data"]["category_count"], 0)

    def test_count_values_require_nonnegative_int32(self) -> None:
        for value in (-1, MAX_INT32 + 1, 1.0, "1", True):
            result = project_site_incident_category_counts([{
                "anomalyCode": "A1", "counts": value,
            }])
            self.assertEqual(result["data"]["invalid_count"], 1)
            self.assertNotIn("active_count", result["data"]["categories"][0]["counts"])
        level = project_site_incident_category_counts([{
            "anomalyCode": "A1", "level": 4,
        }])
        self.assertEqual(level["data"]["invalid_count"], 1)

    def test_client_uses_one_category_fixed_window_and_redacted_projection(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        instant = RealDateTime.fromtimestamp(NOW_MS / 1000, timezone.utc)
        with patch.object(client, "_access_token", return_value="fixture-token"), \
                patch.object(client, "_request_json", return_value={
                    "errorCode": 0, "result": [{"anomalyCode": "A1", "counts": 3}]}) as request, \
                patch("app.openapi.datetime") as clock:
            clock.now.return_value = instant
            clock.side_effect = lambda *args, **kwargs: RealDateTime(*args, **kwargs)
            result = client.read_site_incident_category_counts(SITE, 11)
        start_ms = NOW_MS - 86_400_000
        request.assert_called_once_with(
            "GET", f"/openapi/v1/ctrl/sites/site-id/anomaly/category?filters.startTime={start_ms}"
            f"&filters.endTime={NOW_MS}&category=11",
            token="fixture-token")
        self.assertEqual(result["resource"], "site_incident_category_counts")
        self.assertEqual(result["category"], 11)
        self.assertEqual((result["window_start_ms"], result["window_end_ms"]),
                         (start_ms, NOW_MS))
        self.assertEqual(result["data"]["categories"][0]["anomaly_code"], "A1")
        self.assertNotIn("category", result["data"]["categories"][0])

    def test_client_validates_site_binding_before_request(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client", "secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "incident_category_invalid"):
                client.read_site_incident_category_counts(SITE, 10)
            with self.assertRaisesRegex(OpenApiError, "incident_category_invalid"):
                client.read_site_incident_category_counts(SITE, True)
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_incident_category_counts(SITE, 11)
            with self.assertRaisesRegex(OpenApiError, "site_ref_invalid"):
                client.read_site_incident_category_counts("A" * 24, 11)
        request.assert_not_called()
        route = ("/openapi/v1/ctrl/sites/site-id/anomaly/category?"
                 f"filters.startTime={NOW_MS - 86_400_000}&filters.endTime={NOW_MS}&category=11")
        self.assertTrue(client._site_incident_category_counts_request_valid(route))
        self.assertFalse(client._site_incident_category_counts_request_valid(
            route.replace("/ctrl/", "/other/")))
        self.assertFalse(client._site_incident_category_counts_request_valid(
            route.replace("category=11", "category=20")))
        self.assertFalse(client._site_incident_category_counts_request_valid(
            route.replace(f"filters.endTime={NOW_MS}", f"filters.endTime={NOW_MS - 1}")))
        self.assertFalse(client._site_incident_category_counts_request_valid(route + "?debug=true"))


if __name__ == "__main__":
    unittest.main()
