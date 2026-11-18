from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.wifi_compare_sessions import SessionCompareError, compare_sessions


AP_A, AP_B, AP_C = "a" * 24, "b" * 24, "c" * 24


class WifiCompareSessionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.first = Path(self.temp_dir.name) / "first.jsonl"
        self.second = Path(self.temp_dir.name) / "second.jsonl"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write(self, path: Path, *, interval=5, sample_limit=3, samples=None,
               stop_reason="sample_limit") -> None:
        samples = samples if samples is not None else [
            {"record_type": "sample", "sample_index": 1, "timestamp_ms": 1_800_000_001_000,
             "metrics": {"rssi": -60, "snr": 30, "channel": 44},
             "access_point_ref": AP_A, "ap_assignment_status": "mapped",
             "sample_status": "ok", "partial": False},
            {"record_type": "sample", "sample_index": 2, "timestamp_ms": 1_800_000_006_000,
             "metrics": {"rssi": -55, "snr": 35, "channel": 48},
             "access_point_ref": AP_B, "ap_assignment_status": "mapped",
             "sample_status": "ok", "partial": False},
        ]
        header = {"record_type": "session", "schema_version": 1,
                  "started_at_ms": 1_800_000_000_000,
                  "duration_limit_seconds": 60, "interval_seconds": interval,
                  "sample_limit": sample_limit, "collection": "read_only_connector_poll"}
        footer = {"record_type": "session_end", "finished_at_ms": 1_800_000_010_000,
                  "sample_count": len(samples), "stop_reason": stop_reason}
        path.write_text("\n".join(json.dumps(row, separators=(",", ":"))
                                for row in [header, *samples, footer]) + "\n",
                        encoding="utf-8")
        path.chmod(0o600)

    def test_compares_aligned_signal_samples_and_summarizes_ap_changes(self) -> None:
        self._write(self.first)
        right_samples = [
            {"record_type": "sample", "sample_index": 1, "timestamp_ms": 1_800_000_001_000,
             "metrics": {"rssi": -58, "snr": 31, "channel": 44},
             "access_point_ref": AP_B, "ap_assignment_status": "mapped",
             "sample_status": "ok", "partial": False},
            {"record_type": "sample", "sample_index": 2, "timestamp_ms": 1_800_000_006_000,
             "metrics": {"rssi": -53, "snr": 36, "channel": 48},
             "access_point_ref": AP_C, "ap_assignment_status": "mapped",
             "sample_status": "ok", "partial": False},
        ]
        self._write(self.second, samples=right_samples)

        result = compare_sessions(str(self.first), str(self.second))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["compared_sample_indices"], 2)
        self.assertEqual(result["metric_deltas_second_minus_first"]["rssi"][
            "average_delta_second_minus_first"], 2)
        self.assertEqual(result["categorical_metric_matches"]["channel"]["matching_count"], 2)
        self.assertEqual(result["first"]["ap_changes_observed"], 1)
        self.assertEqual(result["second"]["ap_changes_observed"], 1)
        self.assertEqual(result["ap_reference_comparison"], "not_performed_across_sessions")
        self.assertNotIn(AP_A, repr(result))
        self.assertNotIn(AP_B, repr(result))

    def test_different_sampling_conditions_disable_aligned_deltas(self) -> None:
        self._write(self.first)
        self._write(self.second, interval=10)

        result = compare_sessions(str(self.first), str(self.second))

        self.assertEqual(result["comparison_status"], "conditions_differ")
        self.assertEqual(result["compared_sample_indices"], 0)
        self.assertEqual(result["metric_deltas_second_minus_first"], {})
        self.assertTrue(result["partial"])

    def test_read_gaps_and_not_wireless_samples_are_reported_without_cause(self) -> None:
        self._write(self.first)
        samples = [
            {"record_type": "sample", "sample_index": 1, "timestamp_ms": 1_800_000_001_000,
             "metrics": {}, "access_point_ref": None,
             "ap_assignment_status": "not_applicable", "sample_status": "not_wireless",
             "partial": True},
            {"record_type": "sample", "sample_index": 2, "timestamp_ms": 1_800_000_006_000,
             "metrics": {}, "access_point_ref": None,
             "ap_assignment_status": "unavailable", "sample_status": "read_unavailable",
             "partial": True},
        ]
        self._write(self.second, samples=samples, stop_reason="source_error")

        result = compare_sessions(str(self.first), str(self.second))

        self.assertEqual(result["second"]["not_wireless_samples"], 1)
        self.assertEqual(result["second"]["unavailable_read_samples"], 1)
        self.assertIn("no outage cause", result["interruption_note"])
        self.assertEqual(result["status"], "partial")

    def test_duplicate_json_fields_are_rejected(self) -> None:
        self.first.write_text('{"record_type":"session","record_type":"session"}\n',
                              encoding="utf-8")
        self.first.chmod(0o600)
        self._write(self.second)
        with self.assertRaisesRegex(SessionCompareError, "session_format_invalid"):
            compare_sessions(str(self.first), str(self.second))

    def test_existing_files_must_be_regular_and_owned(self) -> None:
        self._write(self.first)
        self._write(self.second)
        link = Path(self.temp_dir.name) / "linked.jsonl"
        link.symlink_to(self.first)
        with self.assertRaisesRegex(SessionCompareError, "session_file_invalid"):
            compare_sessions(str(link), str(self.second))


if __name__ == "__main__":
    unittest.main()
