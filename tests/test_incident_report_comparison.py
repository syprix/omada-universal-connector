from __future__ import annotations

import unittest

from app.incident_report_comparison import (
    IncidentReportComparisonError, compare_incident_reports,
)
from app.mcp import _tools_page
from app.operation_registry import REGISTRY
from tests.test_site_outage_report import _summary as raw_site_summary
from tools.site_outage_report import project_report


def report(*, start: str = "2026-11-19T09:00:00Z",
           end: str = "2026-11-19T10:00:00Z", event_count: int = 4,
           alert_count: int = 2, disconnected: int = 1,
           observed: str = "2026-11-19T10:01:00Z", partial: bool = False) -> dict[str, object]:
    status = "partial" if partial else "ok"
    return {
        "report_schema_version": 1, "connector_version": "0.3.0-dev",
        "status": status, "window_utc": {"start": start, "end": end},
        "reachability_observed_at_utc": observed,
        "current_reachability": {"status": "ok", "isolated_access_points": 0,
            "missing_field_count": 0, "device_classes": {
            "access_points": {"total": 4, "connected": 4 - disconnected,
                              "disconnected": disconnected},
            "gateways": {"total": 1, "connected": 1, "disconnected": 0},
            "switches": {"total": 2, "connected": 2, "disconnected": 0},
        }},
        "events": {"status": status, "total_count": event_count,
                   "returned_count": event_count, "pagination": {
                       "pages_fetched": 1, "page_limit_reached": False}},
        "alerts": {"status": status, "total_count": alert_count,
                   "returned_count": alert_count, "pagination": {
                       "pages_fetched": 1, "page_limit_reached": False}},
        "scope_assessment": "indeterminate", "limitations": [],
        "partial": partial, "sources": ["site_overview"],
        "live_controller_tested": False,
    }


class IncidentReportComparisonTests(unittest.TestCase):
    def test_accepts_reports_produced_by_the_existing_outage_report_workflow(self) -> None:
        first = project_report(raw_site_summary())
        second = project_report(raw_site_summary())
        result = compare_incident_reports([first, second])
        self.assertEqual(result["supported_report_count"], 2)
        self.assertTrue(all(item["status"] == "comparable"
                            for item in result["comparisons"]))

    def test_mcp_lists_the_bounded_report_comparison_tool(self) -> None:
        tools = []
        for offset in range(0, 1000, 25):
            page = _tools_page(REGISTRY, str(offset) if offset else None)
            tools.extend(page["tools"])
            if "nextCursor" not in page:
                break
        tool = next(item for item in tools if
                    item["name"] == "omada_compare_incident_reports")
        schema = tool["inputSchema"]
        self.assertEqual(schema["required"], ["reports"])
        self.assertEqual(schema["properties"]["reports"]["minItems"], 2)
        self.assertEqual(schema["properties"]["reports"]["maxItems"], 8)
        self.assertTrue(tool["annotations"]["readOnlyHint"])

    def test_compares_counts_only_for_identical_complete_windows(self) -> None:
        first = report()
        second = report(event_count=7, alert_count=5, disconnected=0)
        result = compare_incident_reports([first, second])
        self.assertEqual(result["resource"], "incident_report_comparison")
        self.assertEqual(result["common_time_window_utc"], {
            "start": "2026-11-19T09:00:00Z", "end": "2026-11-19T10:00:00Z"})
        self.assertEqual(result["comparisons"], [
            {"metric": "events", "status": "comparable",
             "values": [{"report_index": 1, "value": 4}, {"report_index": 2, "value": 7}],
             "delta_from_first": [{"report_index": 2, "delta": 3}]},
            {"metric": "alerts", "status": "comparable",
             "values": [{"report_index": 1, "value": 2}, {"report_index": 2, "value": 5}],
             "delta_from_first": [{"report_index": 2, "delta": 3}]},
            {"metric": "current_reachability.disconnected_count", "status": "comparable",
             "values": [{"report_index": 1, "value": 1}, {"report_index": 2, "value": 0}],
             "delta_from_first": [{"report_index": 2, "delta": -1}]},
            {"metric": "current_reachability.isolated_access_points", "status": "comparable",
             "values": [{"report_index": 1, "value": 0}, {"report_index": 2, "value": 0}],
             "delta_from_first": [{"report_index": 2, "delta": 0}]},
        ])
        self.assertEqual(result["live_controller_queries"], 0)

    def test_different_windows_and_snapshot_times_are_not_compared(self) -> None:
        result = compare_incident_reports([
            report(), report(start="2026-11-19T09:30:00Z", event_count=9,
                             observed="2026-11-19T10:02:00Z")])
        self.assertEqual(result["common_time_window_utc"], {
            "start": "2026-11-19T09:30:00Z", "end": "2026-11-19T10:00:00Z"})
        self.assertEqual([item["status"] for item in result["comparisons"]], [
            "window_mismatch", "window_mismatch", "snapshot_time_mismatch",
            "snapshot_time_mismatch"])

    def test_partial_rows_and_pagination_gaps_are_exposed(self) -> None:
        value = report(partial=True)
        value["events"]["pagination"]["page_limit_reached"] = True
        result = compare_incident_reports([value, report()])
        self.assertTrue(result["partial"])
        self.assertEqual(result["reports"][0]["status"], "partial")
        self.assertTrue(result["reports"][0]["pagination_limit_reached"]["events"])
        self.assertEqual(result["comparisons"][0]["status"], "partial_source")

    def test_unsupported_source_is_visible_but_raw_fields_never_escape(self) -> None:
        secret = "private SSID and controller text"
        result = compare_incident_reports([report(), {"resource": "other_report",
                                                       "ssid": secret, "detail": secret}])
        self.assertEqual(result["unsupported_report_count"], 1)
        self.assertEqual(result["reports"][1]["source_status"], "unsupported")
        self.assertNotIn(secret, repr(result))
        self.assertEqual(result["comparisons"][0]["status"], "not_comparable_source")

    def test_rejects_unbounded_or_malformed_collections(self) -> None:
        for items in ([], [report()], [report()] * 9, [report(), report() | {"large": "x" * 62_000}],
                      [report(), None]):
            with self.subTest(size=len(items)), self.assertRaises(IncidentReportComparisonError):
                compare_incident_reports(items)

    def test_unknown_fields_are_counted_without_returning_values(self) -> None:
        item = report()
        item["ssid_name"] = "secret-name"
        result = compare_incident_reports([item, report()])
        self.assertEqual(result["reports"][0]["unknown_field_count"], 1)
        self.assertTrue(result["reports"][0]["partial"])
        self.assertNotIn("secret-name", repr(result))

    def test_malformed_nested_status_values_are_counted_as_partial(self) -> None:
        item = report()
        item["events"]["status"] = []
        item["current_reachability"]["status"] = {}
        result = compare_incident_reports([item, report()])
        self.assertTrue(result["reports"][0]["partial"])
        self.assertEqual(result["reports"][0]["events"]["status"], "unavailable")

    def test_missing_window_or_observation_timestamps_are_reported_as_gaps(self) -> None:
        item = report()
        item["window_utc"] = {"start": "bad", "end": "bad"}
        item["reachability_observed_at_utc"] = None
        result = compare_incident_reports([item, report()])
        self.assertEqual(result["reports"][0]["time_gap_count"], 3)
        self.assertIsNone(result["common_time_window_utc"])
        self.assertTrue(result["reports"][0]["partial"])


if __name__ == "__main__":
    unittest.main()
