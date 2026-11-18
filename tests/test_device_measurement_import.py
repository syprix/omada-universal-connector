from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from app.device_measurement_import import (
    DeviceMeasurementError, import_file, parse_csv, parse_json,
)


class DeviceMeasurementImportTests(unittest.TestCase):
    def _json(self, rows: list[dict[str, object]]) -> str:
        return json.dumps({"schema_version": 1, "samples": rows})

    def _row(self, timestamp="2026-01-01T09:00:00+01:00") -> dict[str, object]:
        return {"timestamp": timestamp, "wifi_connected": True,
                "wifi_source": "system_log"}

    def test_json_normalizes_timezone_and_keeps_independent_source_provenance(self) -> None:
        row = self._row()
        row.update({
            "local_reachability": "reachable",
            "local_reachability_source": "reachability_check",
            "dns_status": "failed", "dns_source": "dns_resolution_check",
            "ipv4_status": "available", "ipv4_source": "interface_status",
            "cellular_transition": "wifi_to_cellular",
            "cellular_transition_source": "system_log",
        })
        result = parse_json(self._json([row]))
        self.assertEqual(result["resource"], "device_measurements")
        self.assertEqual(result["window"], {
            "start_utc": "2026-01-01T08:00:00.000Z",
            "end_utc": "2026-01-01T08:00:00.000Z",
        })
        observation = result["observations"][0]
        self.assertEqual(observation["wifi"], {
            "connected": True, "source_kind": "system_log",
            "verification": "imported_unverified",
        })
        self.assertEqual(observation["dns"]["status"], "failed")
        self.assertEqual(observation["dns"]["source_kind"], "dns_resolution_check")
        self.assertEqual(observation["cellular_transition"]["status"], "wifi_to_cellular")
        self.assertEqual(result["coverage"]["dns"], 1)
        self.assertEqual(result["source_verification"],
                         "declared_sources_not_independently_verified")

    def test_csv_import_is_bounded_and_accepts_only_documented_columns(self) -> None:
        text = (
            "timestamp,wifi_connected,wifi_source,dns_status,dns_source\r\n"
            "2026-01-01T08:00:00Z,false,diagnostic_export,resolved,dns_resolution_check\r\n"
            "2026-01-01T08:00:05Z,true,system_log,,\r\n"
        )
        result = parse_csv(text)
        self.assertEqual(result["sample_count"], 2)
        self.assertFalse(result["observations"][0]["wifi"]["connected"])
        self.assertEqual(result["observations"][0]["dns"]["status"], "resolved")
        self.assertNotIn("dns", result["observations"][1])
        self.assertFalse(result["partial"])

    def test_json_rejects_unknown_fields_and_personal_data_columns(self) -> None:
        row = self._row()
        row["device_name"] = "private name"
        with self.assertRaisesRegex(DeviceMeasurementError, "schema_invalid"):
            parse_json(self._json([row]))
        with self.assertRaisesRegex(DeviceMeasurementError, "csv_header_invalid"):
            parse_csv("timestamp,wifi_connected,wifi_source,ip_address\n"
                      "2026-01-01T08:00:00Z,true,system_log,192.0.2.1\n")

    def test_unknown_or_naive_timezones_and_precision_are_rejected(self) -> None:
        for timestamp, code in [
            ("2026-01-01T09:00:00", "timestamp_invalid"),
            ("2026-01-01T09:00:00-00:00", "timezone_unknown"),
            ("2026-01-01T09:00:00+14:01", "timezone_invalid"),
            ("2026-01-01T09:00:00.000001Z", "timestamp_precision_unsupported"),
            ("1969-12-31T23:59:59.999Z", "timestamp_range_invalid"),
        ]:
            with self.subTest(timestamp=timestamp):
                with self.assertRaisesRegex(DeviceMeasurementError, code):
                    parse_json(self._json([self._row(timestamp)]))

    def test_timestamps_must_be_strictly_increasing_after_millisecond_normalization(self) -> None:
        with self.assertRaisesRegex(DeviceMeasurementError, "timestamps_not_increasing"):
            parse_json(self._json([
                self._row("2026-01-01T08:00:00Z"),
                self._row("2026-01-01T09:00:00+01:00"),
            ]))
        with self.assertRaisesRegex(DeviceMeasurementError, "timestamps_not_increasing"):
            parse_json(self._json([
                self._row("2026-01-01T08:00:01Z"),
                self._row("2026-01-01T08:00:00Z"),
            ]))

    def test_optional_values_require_field_specific_evidence_sources(self) -> None:
        row = self._row()
        row["dns_status"] = "resolved"
        with self.assertRaisesRegex(DeviceMeasurementError, "evidence_pair_incomplete"):
            parse_json(self._json([row]))
        row["dns_source"] = "private app name"
        with self.assertRaisesRegex(DeviceMeasurementError, "evidence_source_invalid"):
            parse_json(self._json([row]))
        row["dns_status"] = None
        row["dns_source"] = None
        with self.assertRaisesRegex(DeviceMeasurementError, "evidence_pair_incomplete"):
            parse_json(self._json([row]))

    def test_status_values_and_wifi_boolean_are_strict(self) -> None:
        row = self._row()
        row["wifi_connected"] = 1
        with self.assertRaisesRegex(DeviceMeasurementError, "wifi_state_invalid"):
            parse_json(self._json([row]))
        row = self._row()
        row.update({"ipv6_status": "maybe", "ipv6_source": "interface_status"})
        with self.assertRaisesRegex(DeviceMeasurementError, "measurement_value_invalid"):
            parse_json(self._json([row]))
        with self.assertRaisesRegex(DeviceMeasurementError, "wifi_state_invalid"):
            parse_csv("timestamp,wifi_connected,wifi_source\n"
                      "2026-01-01T08:00:00Z,yes,system_log\n")

    def test_json_rejects_duplicate_keys_and_unbounded_sample_count(self) -> None:
        with self.assertRaisesRegex(DeviceMeasurementError, "json_invalid"):
            parse_json('{"schema_version":1,"schema_version":1,"samples":[]}')
        with self.assertRaisesRegex(DeviceMeasurementError, "sample_count_invalid"):
            parse_json(self._json([self._row("2026-01-01T08:00:%02dZ" % (i % 60))
                                   for i in range(10_001)]))

    def test_import_file_rejects_symlinks_and_non_owner_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "measurements.json"
            source.write_text(self._json([self._row()]), encoding="utf-8")
            link = root / "alias.json"
            link.symlink_to(source)
            with self.assertRaisesRegex(DeviceMeasurementError, "input_unavailable"):
                import_file(str(link), "json")
            result = import_file(str(source), "json")
            self.assertEqual(result["sample_count"], 1)

    def test_import_file_size_limit_is_enforced_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "too-large.json"
            source.write_bytes(b" " * (2 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(DeviceMeasurementError, "input_invalid"):
                import_file(str(source), "json")

    def test_cli_contract_does_not_echo_input_path_or_raw_fields(self) -> None:
        row = self._row()
        row.update({"local_reachability": "unreachable",
                    "local_reachability_source": "reachability_check"})
        result = parse_json(self._json([row]))
        serialized = json.dumps(result)
        for forbidden in ("device_name", "mac_address", "ip_address", "192.0.2.1"):
            self.assertNotIn(forbidden, serialized)
        self.assertIn("imported_unverified", serialized)


if __name__ == "__main__":
    unittest.main()
