from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from tools.site_outage_report import (
    ReportError, _read_json, _write_new_file, project_report, render_markdown,
)


SITE_REF = "a" * 24


def _summary(*, partial: bool = False) -> dict[str, object]:
    reachability = {"status": "ok", "partial": False, "missing_field_count": 0,
                    "isolated_access_points": 1,
                    "device_classes": {
                        "access_points": {"total": 4, "connected": 3, "disconnected": 1},
                        "gateways": {"total": 1, "connected": 1, "disconnected": 0},
                        "switches": {"total": 2, "connected": 2, "disconnected": 0},
                    }}
    pagination = {"pages_fetched": 1, "page_size": 100, "page_limit": 10,
                  "page_limit_reached": partial}
    events = {"status": "partial" if partial else "ok", "total_count": 3,
              "returned_count": 2 if partial else 3, "module_counts": {"device": 2 if partial else 3},
              "pagination": pagination, "partial": partial}
    alerts = {**events, "severity_counts": {"warning": 2 if partial else 3}}
    return {"status": "partial" if partial else "ok", "resource": "site_outage_summary",
            "site_ref": SITE_REF, "window": {"start_ms": 1_790_000_000_000,
                                                "end_ms": 1_790_000_030_000},
            "reachability_observed_at_ms": 1_790_000_031_000,
            "sections": {"current_reachability": reachability,
                         "events": events, "alerts": alerts}, "partial": partial}


class SiteOutageReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_report_contains_only_allowlisted_counts_and_limits(self) -> None:
        report = project_report(_summary())
        rendered = render_markdown(report)
        encoded = json.dumps(report)
        self.assertEqual(report["status"], "ok")
        self.assertNotIn(SITE_REF, encoded)
        self.assertIn("3 connected / 4 total", rendered)
        self.assertIn("Scope assessment: **indeterminate**", rendered)
        self.assertIn("No outage cause", " ".join(report["limitations"]))
        self.assertFalse(report["live_controller_tested"])

    def test_partial_pagination_survives_export(self) -> None:
        report = project_report(_summary(partial=True))
        self.assertEqual(report["status"], "partial")
        self.assertTrue(report["events"]["pagination"]["page_limit_reached"])
        self.assertIn("pagination reached", render_markdown(report))

    def test_input_must_be_private_regular_local_file_without_duplicate_keys(self) -> None:
        source = self.root / "summary.json"
        source.write_text(json.dumps(_summary()), encoding="utf-8")
        source.chmod(0o600)
        self.assertEqual(project_report(_read_json(str(source)))["status"], "ok")
        link = self.root / "linked.json"
        link.symlink_to(source)
        with self.assertRaisesRegex(ReportError, "input_invalid"):
            _read_json(str(link))
        duplicate = self.root / "duplicate.json"
        duplicate.write_text('{"resource":"x","resource":"y"}', encoding="utf-8")
        duplicate.chmod(0o600)
        with self.assertRaisesRegex(ReportError, "input_invalid"):
            _read_json(str(duplicate))

    def test_output_is_created_private_and_never_overwritten(self) -> None:
        output = self.root / "report.md"
        _write_new_file(str(output), "safe report\n")
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        with self.assertRaisesRegex(ReportError, "output_unavailable"):
            _write_new_file(str(output), "replacement\n")
        self.assertEqual(output.read_text(encoding="utf-8"), "safe report\n")


if __name__ == "__main__":
    unittest.main()
