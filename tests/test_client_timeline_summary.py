from __future__ import annotations

import unittest

from tools.wifi_diagnose import CliError, run, summarize_client_timeline
from tests.test_wifi_diagnose import SITE_REF, _complete_payloads
from tests.test_wifi_diagnose_client import _client


CLIENT_REF = "c" * 24
WINDOW_START = 1_000
WINDOW_END = WINDOW_START + 86_400_000


class ClientTimelineSummaryTests(unittest.TestCase):
    def test_summary_counts_sessions_events_codes_and_time_bounds(self) -> None:
        timeline = {
            "status": "ok", "partial": False, "capability_status": "unknown",
            "window": {"start_ms": 100, "end_ms": 200},
            "data": {"sessions": [
                {"start_ms": 100, "end_ms": 150, "events": [
                    {"time_ms": 110, "event_type": 2},
                    {"time_ms": 140, "event_type": 100},
                ]},
                {"start_ms": 160, "end_ms": 190, "events": [
                    {"time_ms": 170, "event_type": 2},
                ]},
            ]},
        }
        result = summarize_client_timeline(timeline)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["summary"], {
            "session_count": 2, "event_count": 3, "unknown_event_count": 0,
            "by_event_type_code": {"2": 2, "100": 1},
            "first_event_ms": 110, "last_event_ms": 170,
        })
        self.assertNotIn("sessions", repr(result))

    def test_invalid_codes_and_partial_timelines_remain_explicit(self) -> None:
        timeline = {
            "status": "ok", "partial": True, "capability_status": "unknown",
            "window": {"start_ms": 1, "end_ms": 2},
            "data": {"sessions": [{"events": [
                {"time_ms": 1, "event_type": None},
            ]}]},
        }
        result = summarize_client_timeline(timeline)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["summary"]["unknown_event_count"], 1)
        self.assertEqual(result["summary"]["by_event_type_code"], {})
        with self.assertRaisesRegex(CliError, "response_invalid"):
            summarize_client_timeline({"status": "ok", "partial": False, "window": {},
                                       "data": {"sessions": "unbounded"}})

    def test_client_workflow_can_return_compact_timelines_for_agent_calls(self) -> None:
        responses = _complete_payloads()
        responses[f"/v1/sites/{SITE_REF}/clients"] = {
            "status": "ok", "resource": "clients", "site_ref": SITE_REF,
            "count": 1, "items": [_client(CLIENT_REF, channel=36, rssi=-65, snr=25)],
        }
        responses[f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF}/connections"] = {
            "status": "ok", "resource": "client_connection_history", "site_ref": SITE_REF,
            "client_ref": CLIENT_REF, "window_start_ms": WINDOW_START,
            "window_end_ms": WINDOW_END, "count": 0, "items": [],
        }
        for kind in ("connect", "association", "roaming", "disconnect"):
            responses[f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF}/timeline/{kind}"] = {
                "status": "ok", "resource": "client_timeline", "site_ref": SITE_REF,
                "client_ref": CLIENT_REF, "kind": kind, "window_start_ms": WINDOW_START,
                "window_end_ms": WINDOW_END, "data": {"sessions": [{
                    "start_ms": WINDOW_START, "end_ms": WINDOW_END,
                    "events": [{"time_ms": WINDOW_START + 100, "event_type": 2},
                               {"time_ms": WINDOW_START + 200, "event_type": 100}],
                }]}, "partial": False, "missing_fields": [], "omitted_fields": [],
                "omitted_field_count": 0,
            }
        responses[f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF}/health/timeline"] = {
            "status": "ok", "resource": "client_health_timeline", "site_ref": SITE_REF,
            "client_ref": CLIENT_REF, "window_start_ms": WINDOW_START,
            "window_end_ms": WINDOW_END, "data": {"scores": []}, "partial": False,
            "missing_fields": [], "omitted_fields": [], "omitted_field_count": 0,
        }
        responses[f"/v1/sites/{SITE_REF}/clients/{CLIENT_REF}/history"] = {
            "status": "ok", "resource": "client_history", "site_ref": SITE_REF,
            "client_ref": CLIENT_REF, "data": {"count": 0, "rows": []},
            "partial": False, "missing_field_count": 0, "invalid_field_count": 0,
            "unknown_field_count": 0, "omitted_count": 0,
        }
        full = run(SITE_REF, "", requester=lambda path: responses[path],
                   client_ref=CLIENT_REF, client_timeline=True)
        compact = run(SITE_REF, "", requester=lambda path: responses[path],
                      client_ref=CLIENT_REF, client_timeline=True,
                      compact_client_timeline=True, include_wlan_policy_context=False)
        detail = full["client"]["timelines"]["roaming"]
        summary = compact["client"]["timelines"]["roaming"]
        self.assertIn("sessions", detail["data"])
        self.assertNotIn("data", summary)
        self.assertEqual(summary["summary"]["event_count"], 2)
        self.assertEqual(summary["summary"]["by_event_type_code"], {"2": 1, "100": 1})


if __name__ == "__main__":
    unittest.main()
