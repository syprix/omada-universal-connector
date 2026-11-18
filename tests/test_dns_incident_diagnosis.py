from __future__ import annotations

import datetime as dt
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from app.config_snapshots import build_snapshot
from app.device_measurement_import import parse_json
from app.dns_incident_diagnosis import (
    DnsIncidentDiagnosisError, diagnose_dns_incident,
)
from tools.diagnose_dns_incident import main as diagnose_cli


def ms(value: str) -> int:
    stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(stamp.timestamp() * 1000)


class DnsIncidentDiagnosisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {"timestamp": "2026-11-18T10:00:00Z", "wifi_connected": True,
             "wifi_source": "diagnostic_export", "dns_status": "failed",
             "dns_source": "dns_resolution_check", "local_reachability": "reachable",
             "local_reachability_source": "reachability_check", "ipv4_status": "available",
             "ipv4_source": "interface_status"},
            {"timestamp": "2026-11-18T10:01:00Z", "wifi_connected": False,
             "wifi_source": "system_log", "dns_status": "failed",
             "dns_source": "diagnostic_export", "local_reachability": "unreachable",
             "local_reachability_source": "diagnostic_export", "ipv6_status": "unavailable",
             "ipv6_source": "interface_status"},
            {"timestamp": "2026-11-18T10:02:00Z", "wifi_connected": True,
             "wifi_source": "diagnostic_export", "dns_status": "resolved",
             "dns_source": "diagnostic_export", "local_reachability": "unreachable",
             "local_reachability_source": "reachability_check"},
            {"timestamp": "2026-11-18T10:03:00Z", "wifi_connected": True,
             "wifi_source": "system_log"},
            {"timestamp": "2026-11-18T10:04:00Z", "wifi_connected": True,
             "wifi_source": "system_log", "dns_status": "failed",
             "dns_source": "diagnostic_export"},
        ]
        self.measurements = parse_json(json.dumps({
            "schema_version": 1, "samples": self.rows}))
        self.start, self.end = ms("2026-11-18T10:00:00Z"), ms("2026-11-18T10:03:00Z")
        self.snapshot = build_snapshot(site_label="home", sections=[{
            "kind": "dns", "label": "site", "status": "observed", "partial": False,
            "values": {"cache_enabled": True, "cache_ttl_seconds": 300,
                       "proxy_enabled": True, "proxy_mode": "doh",
                       "supports_dns_override": False, "dns_override_configured": False},
        }], captured_at="2026-11-18T10:02:00Z")
        self.network = {
            "status": "ok", "resource": "ssid_network_summary", "ssid_count": 2,
            "network_count": 2, "matched_count": 2, "partial": False,
            "network_checks": {"dns": {"status": "observed",
                                         "network_specific_mapping": "unknown"}},
        }

    def test_reports_observations_and_cross_source_disagreements_without_cause(self) -> None:
        report = diagnose_dns_incident(
            self.measurements, start_ms=self.start, end_ms=self.end,
            snapshot=self.snapshot, network_summary=self.network,
            include_observations=True)
        summary = report["summary"]
        self.assertEqual(summary["sample_count"], 4)
        self.assertEqual(summary["dns_failed_count"], 2)
        self.assertEqual(summary["dns_resolved_count"], 1)
        self.assertEqual(summary["dns_missing_count"], 1)
        self.assertEqual(summary["dns_failure_with_local_reachable_count"], 1)
        self.assertEqual(summary["dns_failure_with_local_unreachable_count"], 1)
        self.assertEqual(summary["dns_failure_with_wifi_disconnected_count"], 1)
        self.assertEqual(summary["dns_resolved_with_local_unreachable_count"], 1)
        self.assertEqual(report["cause"], "undetermined")
        self.assertEqual(report["dns_configuration"]["status"], "observed")
        self.assertEqual(report["dns_configuration"]["capture_relation_to_window"], "within_window")
        self.assertEqual(report["network_context"]["device_to_network_association"],
                         "unknown_without_imported_network_reference")
        self.assertTrue(report["partial"])
        self.assertEqual(report["observations"][0]["dns"]["verification"], "imported_unverified")

    def test_missing_context_and_empty_window_remain_unknown_and_partial(self) -> None:
        report = diagnose_dns_incident(
            self.measurements, start_ms=ms("2026-11-18T10:10:00Z"),
            end_ms=ms("2026-11-18T10:11:00Z"))
        self.assertEqual(report["summary"]["sample_count"], 0)
        self.assertEqual(report["dns_configuration"]["status"], "unknown")
        self.assertEqual(report["network_context"]["status"], "unknown")
        self.assertEqual(report["cause"], "undetermined")
        self.assertTrue(report["partial"])

    def test_context_and_window_validation_fail_closed(self) -> None:
        with self.assertRaisesRegex(DnsIncidentDiagnosisError, "time_window_invalid"):
            diagnose_dns_incident(self.measurements, start_ms=self.start, end_ms=self.start - 1)
        with self.assertRaisesRegex(DnsIncidentDiagnosisError, "snapshot_invalid"):
            diagnose_dns_incident(self.measurements, start_ms=self.start, end_ms=self.end,
                                  snapshot={"resource": "wrong"})
        with self.assertRaisesRegex(DnsIncidentDiagnosisError, "network_summary_invalid"):
            diagnose_dns_incident(self.measurements, start_ms=self.start, end_ms=self.end,
                                  network_summary={"resource": "wrong"})

    def test_cli_reads_owner_file_and_returns_a_local_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.json"
            path.write_text(json.dumps({"schema_version": 1, "samples": self.rows}),
                            encoding="utf-8")
            path.chmod(0o600)
            output = io.StringIO()
            with redirect_stdout(output):
                status = diagnose_cli(["--measurements", str(path), "--format", "json"])
        self.assertEqual(status, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["resource"], "dns_incident_diagnosis")
        self.assertEqual(report["summary"]["dns_failed_count"], 3)
        self.assertEqual(report["cause"], "undetermined")
        self.assertEqual(report["observation_detail"], "aggregated_only")


if __name__ == "__main__":
    unittest.main()
