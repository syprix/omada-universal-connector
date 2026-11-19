from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_incident_report_comparison import report
from tools.compare_site_outage_reports import main


class CompareSiteOutageReportsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = []
        for index, item in enumerate((report(), report(event_count=8)), 1):
            path = self.root / f"report-{index}.json"
            path.write_text(json.dumps(item), encoding="utf-8")
            path.chmod(0o600)
            self.paths.append(path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_cli_reads_existing_private_files_and_emits_redacted_json(self) -> None:
        output = io.StringIO()
        args = ["--input", str(self.paths[0]), "--input", str(self.paths[1]),
                "--format", "json"]
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(args), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value["resource"], "incident_report_comparison")
        self.assertEqual(value["live_controller_queries"], 0)

    def test_output_file_is_private_and_never_overwritten(self) -> None:
        target = self.root / "comparison.json"
        args = ["--input", str(self.paths[0]), "--input", str(self.paths[1]),
                "--output", str(target), "--format", "json"]
        self.assertEqual(main(args), 0)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        target.write_text("keep", encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(args), 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")
        self.assertIn("output_unavailable", err.getvalue())

    def test_cli_rejects_non_private_input_files(self) -> None:
        self.paths[0].chmod(0o644)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(["--input", str(self.paths[0]), "--input",
                                   str(self.paths[1]), "--format", "json"]), 2)
        self.assertIn("input_invalid", err.getvalue())


if __name__ == "__main__":
    unittest.main()
