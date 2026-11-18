from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from app.device_measurement_compare import (
    DeviceMeasurementCompareError, compare_device_sources,
)


BASE_MS = 1_800_000_000_000
SITE_REF = "a" * 24
CLIENT_REF = "b" * 24
AP_REF = "c" * 24


class DeviceMeasurementCompareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.device = root / "measurements.json"
        self.timeline = root / "client-timeline.json"
        self.session = root / "walk-session.jsonl"
        self.device.write_text(json.dumps({"schema_version": 1, "samples": [
            {"timestamp": "2027-01-15T08:00:00.000Z", "wifi_connected": True,
             "wifi_source": "system_log", "dns_status": "failed",
             "dns_source": "dns_resolution_check"},
            {"timestamp": "2027-01-15T08:00:05.000Z", "wifi_connected": True,
             "wifi_source": "diagnostic_export", "local_reachability": "reachable",
             "local_reachability_source": "reachability_check"},
        ]}), encoding="utf-8")
        self._write_timeline()
        self._write_session()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _write_timeline(self, *, start=BASE_MS - 1000, end=BASE_MS + 6000,
                        extra_event=None, include_private=True, partial=False) -> None:
        events = [{"time_ms": BASE_MS + 100, "event_type": 201,
                   "access_point_ref": AP_REF}]
        if extra_event is not None:
            events.append(extra_event)
        timeline = {"status": "partial" if partial else "ok", "partial": partial,
                    "window": {"start_ms": start, "end_ms": end},
                    "data": {"sessions": [{"events": events}]}}
        timelines = {kind: {**timeline, "data": {"sessions": [{"events":
                     events if kind == "association" else []}]}}
                     for kind in ("connect", "association", "roaming", "disconnect")}
        report = {"status": "ok", "site_ref": SITE_REF,
                  "client": {"status": "ok", "selection": "Private device label",
                             "client_ref": CLIENT_REF, "timelines": timelines}}
        if include_private:
            report["private_ip"] = "192.0.2.44"
            report["client"]["private_name"] = "Private name"
            report["client"]["timelines"]["association"]["data"]["sessions"][0]["events"][0]["ssid"] = "Private SSID"
        self.timeline.write_text(json.dumps(report), encoding="utf-8")

    def _write_session(self, *, first_status="not_wireless", second_status="ok",
                       sample_times=(BASE_MS + 50, BASE_MS + 4950), partial=False,
                       stop_reason="sample_limit", finished=BASE_MS + 6000) -> None:
        header = {"record_type": "session", "schema_version": 1,
                  "started_at_ms": BASE_MS - 1000, "duration_limit_seconds": 20,
                  "interval_seconds": 5, "sample_limit": 10,
                  "collection": "read_only_connector_poll"}
        samples = []
        for index, (timestamp, state) in enumerate(zip(sample_times,
                                                      (first_status, second_status)), start=1):
            is_wireless = state in {"ok", "incomplete"}
            samples.append({"record_type": "sample", "sample_index": index,
                            "timestamp_ms": timestamp,
                            "metrics": {"rssi": -58, "snr": 28} if is_wireless else {},
                            "access_point_ref": AP_REF if is_wireless else None,
                            "ap_assignment_status": "mapped" if is_wireless else "not_applicable",
                            "sample_status": state, "partial": partial or not is_wireless})
        footer = {"record_type": "session_end", "finished_at_ms": finished,
                  "sample_count": len(samples), "stop_reason": stop_reason}
        self.session.write_text("\n".join(json.dumps(row) for row in [header, *samples, footer]) + "\n",
                                encoding="utf-8")

    def _compare(self, **kwargs):
        options = {"device_path": str(self.device), "device_format": "json",
                   "timeline_path": str(self.timeline), "session_path": str(self.session),
                   "start_ms": BASE_MS, "end_ms": BASE_MS + 5000,
                   "tolerance_ms": 200, "as_of_ms": BASE_MS + 20_000}
        options.update(kwargs)
        return compare_device_sources(**options)

    def test_joins_only_inside_explicit_window_and_reports_disagreement_without_cause(self):
        result = self._compare()
        self.assertEqual(result["resource"], "device_measurement_comparison")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["window"], {"start_ms": BASE_MS,
                                             "end_ms": BASE_MS + 5000,
                                             "tolerance_ms": 200,
                                             "as_of_ms": BASE_MS + 20_000})
        comparison = result["comparison"]
        self.assertEqual(comparison["wifi_state_disagreements"], 1)
        self.assertEqual(comparison["wifi_state_agreements"], 1)
        first, second = comparison["observations"]
        self.assertEqual(first["client_timeline"]["kind"], "association")
        self.assertEqual(first["client_timeline"]["event_type_code"], 201)
        self.assertEqual(first["wifi_state_relation_to_passive_sample"], "disagrees")
        self.assertEqual(second["wifi_state_relation_to_passive_sample"], "agrees")
        self.assertEqual(result["source_freshness"]["client_timeline"]["age_ms"], None)
        self.assertEqual(result["source_freshness"]["passive_wlan_session"]["age_ms"],
                         BASE_MS + 20_000 - (BASE_MS + 4950))
        self.assertEqual(result["interpretation"], "observations_only_no_cause_inferred")
        encoded = json.dumps(result)
        for private in (SITE_REF, CLIENT_REF, AP_REF, "192.0.2.44", "Private name", "Private SSID"):
            self.assertNotIn(private, encoded)

    def test_no_match_and_equal_distance_are_reported_without_guessing(self):
        self._write_session(sample_times=(BASE_MS + 6000, BASE_MS + 12_000),
                            finished=BASE_MS + 12_000)
        result = self._compare(tolerance_ms=100)
        self.assertEqual(result["comparison"]["observations"][0]["passive_wlan_session"]["status"],
                         "no_match_within_tolerance")
        self.assertEqual(result["status"], "partial")

        self._write_session(sample_times=(BASE_MS - 100, BASE_MS + 100),
                            finished=BASE_MS + 6000)
        result = self._compare(start_ms=BASE_MS - 1000, end_ms=BASE_MS + 6000,
                               tolerance_ms=100)
        self.assertEqual(result["comparison"]["observations"][0]["passive_wlan_session"]["status"],
                         "ambiguous_nearest")
        self.assertEqual(result["comparison"]["observations"][0]["passive_wlan_session"]["candidate_count"],
                         2)

    def test_partial_or_incomplete_windows_are_explicit(self):
        self._write_timeline(start=BASE_MS + 1000, end=BASE_MS + 6000, partial=True)
        self._write_session(partial=True)
        result = self._compare()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["source_coverage"]["client_timeline"]["windows"]["connect"]["coverage"],
                         "does_not_cover_requested_window")
        self.assertTrue(result["source_coverage"]["passive_wlan_session"]["partial"])

    def test_imported_samples_outside_window_are_counted_but_not_compared(self):
        payload = json.loads(self.device.read_text(encoding="utf-8"))
        payload["samples"].append({"timestamp": "2027-01-15T08:00:06.000Z",
                                   "wifi_connected": True, "wifi_source": "system_log"})
        self.device.write_text(json.dumps(payload), encoding="utf-8")
        result = self._compare()
        coverage = result["source_coverage"]["device_measurements"]
        self.assertEqual(coverage["sample_count_in_window"], 2)
        self.assertEqual(coverage["excluded_outside_window_count"], 1)
        self.assertEqual(result["comparison"]["device_sample_count"], 2)

    def test_bad_windows_and_tolerances_are_rejected(self):
        with self.assertRaisesRegex(DeviceMeasurementCompareError, "time_window_invalid"):
            self._compare(start_ms=BASE_MS + 1, end_ms=BASE_MS)
        with self.assertRaisesRegex(DeviceMeasurementCompareError, "tolerance_invalid"):
            self._compare(tolerance_ms=30_001)
        with self.assertRaisesRegex(DeviceMeasurementCompareError, "time_window_invalid"):
            self._compare(end_ms=BASE_MS + 86_400_001)

    def test_private_timeline_fields_are_ignored_and_malformed_reports_rejected(self):
        self._write_timeline(extra_event={"time_ms": BASE_MS + 300,
                                          "event_type": "private name",
                                          "mac": "11:22:33:44:55:66"})
        result = self._compare()
        self.assertNotIn("11:22:33:44:55:66", json.dumps(result))
        self.timeline.write_text(json.dumps({"client": {"timelines": []}}), encoding="utf-8")
        with self.assertRaisesRegex(DeviceMeasurementCompareError, "timeline_format_invalid"):
            self._compare()

    def test_unavailable_session_samples_do_not_produce_false_wifi_conclusions(self):
        self._write_session(first_status="read_unavailable", second_status="read_unavailable")
        result = self._compare()
        self.assertEqual(result["comparison"]["wifi_state_unassessable"], 2)
        self.assertEqual(result["comparison"]["wifi_state_disagreements"], 0)


if __name__ == "__main__":
    unittest.main()
