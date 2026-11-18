from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_incident_list import (
    MAX_INT32, MAX_INT64, PAGE_SIZE, WINDOW_MS,
    SiteIncidentListError, project_site_incident_list,
)


SITE = "a" * 24


def complete_result() -> dict[str, object]:
    return {
        "totalRows": 63,
        "currentPage": 1,
        "currentSize": PAGE_SIZE,
        "data": [{
            "anomalyCode": "01001001", "category": 11, "level": 2,
            "count": 4, "status": 0, "firstTime": 1_800_000_000_000,
            "lastTime": 1_800_000_001_000, "object": ["private AP"],
            "titleParams": {"name": "private client"},
        }],
    }


class SiteIncidentListTests(unittest.TestCase):
    def test_projects_bounded_records_and_pagination_without_identities(self) -> None:
        result = project_site_incident_list(complete_result())
        self.assertEqual(result["data"]["total_rows"], 63)
        self.assertTrue(result["data"]["has_more"])
        self.assertEqual(result["data"]["returned_count"], 1)
        incident = result["data"]["incidents"][0]
        self.assertEqual(incident["anomaly_code"], "01001001")
        self.assertEqual(incident["occurrence_count"], 4)
        self.assertNotIn("private AP", repr(result))
        self.assertNotIn("private client", repr(result))
        self.assertTrue(result["partial"])

    def test_redacts_unknown_fields_and_marks_invalid_or_missing(self) -> None:
        result = project_site_incident_list({
            "data": [{"anomalyCode": "bad code", "level": 9,
                      "count": True, "object": ["secret"]}],
            "secretTopLevel": "do not echo",
        })
        self.assertIsNone(result["data"]["incidents"][0]["anomaly_code"])
        self.assertEqual(result["data"]["invalid_count"], 3)
        self.assertEqual(result["data"]["unknown_field_count"], 2)
        self.assertGreater(result["data"]["missing_count"], 0)
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("do not echo", repr(result))

    def test_rejects_oversized_rows_and_bad_envelopes(self) -> None:
        for value in (None, [], {str(i): i for i in range(13)},
                      {"data": [{}] * (PAGE_SIZE + 1)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                    SiteIncidentListError):
                project_site_incident_list(value)

    def test_validates_numeric_ranges_and_status_codes(self) -> None:
        for field, value in (("count", -1), ("count", MAX_INT32 + 1),
                             ("lastTime", MAX_INT64 + 1), ("status", 3),
                             ("level", 4), ("firstTime", 1.0)):
            row = {"anomalyCode": "A1", field: value}
            result = project_site_incident_list({"data": [row]})
            self.assertGreater(result["data"]["invalid_count"], 0)
            self.assertTrue(result["partial"])

    def test_client_uses_fixed_page_and_trailing_day(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        fixed = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
        end_ms = int(fixed.timestamp() * 1000)
        with patch("app.openapi.datetime") as clock, \
                patch.object(client, "_access_token", return_value="fixture-token"), \
                patch.object(client, "_request_json", return_value={
                    "errorCode": 0, "result": complete_result()}) as request:
            clock.now.return_value = fixed
            result = client.read_site_incident_list(SITE)
        request.assert_called_once_with(
            "GET",
            f"/openapi/v1/ctrl/sites/site-id/anomaly/incidents?page=1&pageSize=50&"
            f"filters.startTime={end_ms-WINDOW_MS}&filters.endTime={end_ms}",
            token="fixture-token")
        self.assertEqual(result["resource"], "site_incident_list")

    def test_client_rejects_unknown_site_and_invalid_request_shapes(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client", "secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_incident_list(SITE)
        request.assert_not_called()
        start = 1_800_000_000_000
        end = start + WINDOW_MS
        base = "/openapi/v1/ctrl/sites/site-id/anomaly/incidents?page=1&pageSize=50"
        good = f"{base}&filters.startTime={start}&filters.endTime={end}"
        self.assertTrue(client._site_incident_list_request_valid(good))
        self.assertFalse(client._site_incident_list_request_valid(good.replace("/ctrl/", "/other/")))
        self.assertFalse(client._site_incident_list_request_valid(good + "&filters.status=0"))


if __name__ == "__main__":
    unittest.main()
