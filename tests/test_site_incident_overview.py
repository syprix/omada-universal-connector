from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_incident_overview import (
    CATEGORY_FIELDS, COUNT_FIELDS, MAX_CATEGORIES, SiteIncidentOverviewError,
    WINDOW_MS, project_site_incident_overview,
)


SITE = "a" * 24


def complete_result() -> dict[str, object]:
    return {
        **{name: index for index, name in enumerate(COUNT_FIELDS)},
        "anomalyCategoryEventCounts": [{
            "anomalyCode": "01001001",
            **{name: index for index, name in enumerate(CATEGORY_FIELDS)},
        }],
    }


class SiteIncidentOverviewTests(unittest.TestCase):
    def test_projects_only_validated_counts_and_category_code(self) -> None:
        result = project_site_incident_overview(complete_result())
        self.assertEqual(result["data"]["present_count"], len(COUNT_FIELDS))
        self.assertEqual(result["data"]["counts"]["all_status"], 0)
        self.assertEqual(result["data"]["category_counts"][0]["anomaly_code"], "01001001")
        self.assertEqual(result["data"]["category_counts"][0]["active_count"], 0)
        self.assertFalse(result["partial"])

    def test_missing_invalid_and_unknown_fields_mark_partial_without_echo(self) -> None:
        result = project_site_incident_overview({
            "unresolved": True,
            "security": -1,
            "newSensitiveField": "private value",
            "anomalyCategoryEventCounts": [{
                "anomalyCode": "bad code",
                "counts": "unknown",
                "privateLabel": "do not return",
            }],
        })
        self.assertNotIn("unresolved", result["data"]["counts"])
        self.assertNotIn("security", result["data"]["counts"])
        self.assertEqual(result["data"]["invalid_count"], 4)
        self.assertEqual(result["data"]["unknown_field_count"], 2)
        self.assertNotIn("private value", repr(result))
        self.assertNotIn("do not return", repr(result))
        self.assertTrue(result["partial"])

    def test_missing_nested_category_fields_contribute_to_partial_counts(self) -> None:
        payload = {**{name: 0 for name in COUNT_FIELDS},
                   "anomalyCategoryEventCounts": [{"anomalyCode": "01001001"}]}
        result = project_site_incident_overview(payload)
        self.assertEqual(result["data"]["missing_count"], len(CATEGORY_FIELDS))
        self.assertTrue(result["partial"])

    def test_rejects_invalid_envelope_and_oversized_category_list(self) -> None:
        with self.assertRaises(SiteIncidentOverviewError):
            project_site_incident_overview(None)
        with self.assertRaises(SiteIncidentOverviewError):
            project_site_incident_overview({str(i): i for i in range(33)})
        oversized = project_site_incident_overview(
            {"anomalyCategoryEventCounts": [{}] * (MAX_CATEGORIES + 1)})
        self.assertEqual(oversized["data"]["category_counts"], [])
        self.assertEqual(oversized["data"]["invalid_count"], 1)
        self.assertTrue(oversized["partial"])

    def test_client_uses_fixed_site_bound_24_hour_window(self) -> None:
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
            result = client.read_site_incident_overview(SITE)
        request.assert_called_once_with(
            "GET",
            f"/openapi/v1/ctrl/sites/site-id/anomaly/overview/statistics?"
            f"filters.startTime={end_ms-WINDOW_MS}&filters.endTime={end_ms}",
            token="fixture-token")
        self.assertEqual(result["window_end_ms"], end_ms)
        self.assertEqual(result["window_start_ms"], end_ms - WINDOW_MS)
        self.assertEqual(result["resource"], "site_incident_overview")

    def test_client_rejects_unknown_site_and_invalid_internal_time_windows(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client", "secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_incident_overview(SITE)
        request.assert_not_called()
        base = "/openapi/v1/ctrl/sites/site-id/anomaly/overview/statistics"
        start = 1_800_000_000_000
        end = start + WINDOW_MS
        good = f"{base}?filters.startTime={start}&filters.endTime={end}"
        self.assertTrue(client._site_incident_overview_request_valid(good))
        for path in (
            f"{base}?filters.startTime={start}&filters.endTime={end+1}",
            f"{base}?filters.endTime={end}&filters.startTime={start}",
            good.replace("/ctrl/", "/other/"),
            good + "&filters.startTime=1",
        ):
            with self.subTest(path=path):
                self.assertFalse(client._site_incident_overview_request_valid(path))


if __name__ == "__main__":
    unittest.main()
