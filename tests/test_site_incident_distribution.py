from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_incident_distribution import (
    COUNT_FIELDS, MAX_INT32, MAX_INT64, MAX_POINTS, WINDOW_MS,
    SiteIncidentDistributionError, project_site_incident_distribution,
)


SITE = "a" * 24


def complete_result() -> dict[str, object]:
    row = {source: i for i, source in enumerate(COUNT_FIELDS, start=1)}
    row["time"] = 1_800_000_000
    return {"incidentCounts": [row]}


class SiteIncidentDistributionTests(unittest.TestCase):
    def test_projects_documented_counts_and_time(self) -> None:
        result = project_site_incident_distribution(complete_result())
        self.assertEqual(result["data"]["point_count"], 1)
        point = result["data"]["points"][0]
        self.assertEqual(point["time_seconds"], 1_800_000_000)
        self.assertEqual(point["counts"]["wireless_network"],
                         list(COUNT_FIELDS).index("wirelessNetwork") + 1)
        self.assertFalse(result["partial"])

    def test_caps_points_and_omits_unknown_response_content(self) -> None:
        row = complete_result()["incidentCounts"][0]
        result = project_site_incident_distribution({
            "incidentCounts": [row] * MAX_POINTS,
            "privateMessage": "must not be returned",
        })
        self.assertEqual(result["data"]["point_count"], MAX_POINTS)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("privateMessage", repr(result))
        self.assertNotIn("must not be returned", repr(result))
        self.assertTrue(result["partial"])
        with self.assertRaises(SiteIncidentDistributionError):
            project_site_incident_distribution({"incidentCounts": [row] * (MAX_POINTS + 1)})

    def test_accepts_live_143_point_day_within_bounded_limit(self) -> None:
        row = complete_result()["incidentCounts"][0]
        result = project_site_incident_distribution({"incidentCounts": [row] * 143})
        self.assertEqual(result["data"]["point_count"], 143)
        self.assertFalse(result["partial"])

    def test_marks_missing_invalid_and_unknown_fields_partial(self) -> None:
        result = project_site_incident_distribution({
            "incidentCounts": [{"critical": True, "time": MAX_INT64 + 1, "mac": "private"}]
        })
        point = result["data"]["points"][0]
        self.assertNotIn("critical", point["counts"])
        self.assertIsNone(point["time_seconds"])
        self.assertEqual(result["data"]["invalid_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertGreater(result["data"]["missing_count"], 0)
        self.assertTrue(result["partial"])
        self.assertEqual(project_site_incident_distribution({})["data"]["missing_count"], 1)

    def test_rejects_invalid_envelopes_and_bad_count_values(self) -> None:
        for value in (None, [], {str(i): i for i in range(9)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                    SiteIncidentDistributionError):
                project_site_incident_distribution(value)
        row = complete_result()["incidentCounts"][0]
        for value in (-1, MAX_INT32 + 1, 1.0, "2", True):
            with self.subTest(value=value):
                bad = dict(row, critical=value)
                self.assertEqual(project_site_incident_distribution({
                    "incidentCounts": [bad]})["data"]["invalid_count"], 1)

    def test_client_uses_fixed_trailing_day_and_documented_route(self) -> None:
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
            result = client.read_site_incident_distribution(SITE)
        request.assert_called_once_with(
            "GET",
            f"/openapi/v1/ctrl/sites/site-id/anomaly/overview/incident-distribution?"
            f"filters.startTime={end_ms-WINDOW_MS}&filters.endTime={end_ms}",
            token="fixture-token")
        self.assertEqual(result["resource"], "site_incident_distribution")
        self.assertEqual(result["window_end_ms"], end_ms)

    def test_client_rejects_unknown_site_and_invalid_window_before_request(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client", "secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_incident_distribution(SITE)
        request.assert_not_called()
        base = "/openapi/v1/ctrl/sites/site-id/anomaly/overview/incident-distribution"
        start = 1_800_000_000_000
        end = start + WINDOW_MS
        self.assertTrue(client._site_incident_distribution_request_valid(
            f"{base}?filters.startTime={start}&filters.endTime={end}"))
        self.assertFalse(client._site_incident_distribution_request_valid(
            f"{base}?filters.startTime={start}&filters.endTime={end+1}"))
        self.assertFalse(client._site_incident_distribution_request_valid(
            f"/openapi/v1/other/sites/site-id/anomaly/overview/incident-distribution?"
            f"filters.startTime={start}&filters.endTime={end}"))


if __name__ == "__main__":
    unittest.main()
