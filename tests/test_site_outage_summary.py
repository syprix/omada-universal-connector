from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient
from app.site_outage_summary import project_site_outage_summary


SITE_REF = "a" * 24
START, END = 1_790_000_000_000, 1_790_000_030_000


def _logs(resource: str) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "ok", "resource": resource, "site_ref": SITE_REF,
        "window_start_ms": START, "window_end_ms": END,
        "returned_count": 2, "total_count": 2, "partial": False,
        "module_counts": {"device": 2},
        "pagination": {"pages_fetched": 1, "page_size": 100, "page_limit": 10,
                       "page_limit_reached": False},
    }
    if resource.endswith("alerts_window_summary"):
        result["severity_counts"] = {"critical": 1, "warning": 1}
    return result


class SiteOutageSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.overview = {
            "status": "ok", "resource": "site_overview", "site_ref": SITE_REF,
            "data": {"aps_total": 4, "aps_connected": 2, "aps_disconnected": 1,
                     "aps_isolated": 1, "gateways_total": 1,
                     "gateways_connected": 1, "gateways_disconnected": 0,
                     "switches_total": 2, "switches_connected": 2,
                     "switches_disconnected": 0, "clients_total": 12},
        }

    def test_summary_keeps_snapshot_separate_and_does_not_assign_a_cause(self) -> None:
        result = project_site_outage_summary(
            SITE_REF, START, END, self.overview, _logs("site_events_window_summary"),
            _logs("site_alerts_window_summary"), END + 1000)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["reachability_observed_at_ms"], END + 1000)
        self.assertEqual(result["sections"]["current_reachability"]["device_classes"]
                         ["access_points"]["disconnected"], 1)
        self.assertEqual(result["sections"]["events"]["total_count"], 2)
        self.assertEqual(result["sections"]["alerts"]["severity_counts"]["critical"], 1)
        self.assertEqual(result["scope_assessment"]["status"], "indeterminate")
        self.assertNotIn("cause", result)

    def test_missing_snapshot_fields_and_partial_logs_are_marked_partial(self) -> None:
        incomplete = {**self.overview, "data": {"aps_total": 4}}
        events = _logs("site_events_window_summary")
        events["total_count"] = 4
        events["partial"] = True
        events["pagination"]["page_limit_reached"] = True
        result = project_site_outage_summary(
            SITE_REF, START, END, incomplete, events,
            _logs("site_alerts_window_summary"), END)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["sections"]["current_reachability"]["partial"])
        self.assertTrue(result["sections"]["events"]["partial"])
        self.assertTrue(result["partial"])

    def test_unavailable_sources_are_explicit(self) -> None:
        result = project_site_outage_summary(
            SITE_REF, START, END, None, None, _logs("site_alerts_window_summary"), END)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["sections"]["current_reachability"]["status"], "unavailable")
        self.assertEqual(result["sections"]["events"],
                         {"status": "unavailable", "partial": True})

    def test_missing_overview_has_no_snapshot_timestamp(self) -> None:
        result = project_site_outage_summary(
            SITE_REF, START, END, None, _logs("site_events_window_summary"),
            _logs("site_alerts_window_summary"), None)
        self.assertIsNone(result["reachability_observed_at_ms"])

    def test_openapi_workflow_reads_only_the_three_bounded_sources(self) -> None:
        client = object.__new__(OmadaOpenApiClient)
        calls: list[tuple[object, ...]] = []

        def overview(ref: str):
            calls.append(("overview", ref))
            return self.overview

        def logs(ref: str, kind: str, start: int, end: int):
            calls.append((kind, ref, start, end))
            return _logs(f"site_{kind}_window_summary")

        with patch.object(client, "read_site_overview", side_effect=overview), \
                patch.object(client, "read_site_log_window_summary", side_effect=logs):
            result = client.read_site_outage_summary(SITE_REF, START, END)

        self.assertEqual([item[0] for item in calls], ["overview", "events", "alerts"])
        self.assertEqual(result["status"], "ok")


if __name__ == "__main__":
    unittest.main()
