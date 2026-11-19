#!/usr/bin/env python3
"""Compare existing redacted site-outage report files without live reads."""
from __future__ import annotations

import argparse
import json
import sys

try:
    from ..app.incident_report_comparison import (
        IncidentReportComparisonError, compare_incident_reports,
    )
    from .site_outage_report import ReportError, _read_json, _write_new_file
except ImportError:
    from app.incident_report_comparison import (
        IncidentReportComparisonError, compare_incident_reports,
    )
    from tools.site_outage_report import ReportError, _read_json, _write_new_file


def render_markdown(report: dict[str, object]) -> str:
    lines = ["# Incident report comparison", "",
             f"Reports: {report['report_count']}; supported: {report['supported_report_count']}; "
             f"unsupported: {report['unsupported_report_count']}",
             f"Common UTC window: {report['common_time_window_utc'] or 'not available'}", "",
             "## Reports"]
    for item in report["reports"]:
        lines.append(f"- Report {item['report_index']}: {item['source_status']}; "
                     f"status {item.get('status', item.get('reason', 'unknown'))}; "
                     f"window {item.get('window_utc') or 'unavailable'}")
        for section in ("events", "alerts"):
            value = item.get(section, {})
            if isinstance(value, dict) and value.get("total_count") is not None:
                lines.append(f"  - {section.title()}: {value['total_count']} total; "
                             f"{value['returned_count']} returned")
        if item.get("partial"):
            lines.append("  - Coverage is partial or includes unknown fields.")
    lines.extend(["", "## Metric comparisons"])
    for item in report["comparisons"]:
        lines.append(f"- {item['metric']}: {item['status']}")
        if item["status"] == "comparable":
            lines.extend(f"  - Report {row['report_index']}: {row['value']}"
                         for row in item["values"])
    lines.extend(["", "No controller queries were made.", ""])
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True,
                        help="Existing private redacted report JSON; repeat 2–8 times.")
    parser.add_argument("--output")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if not 2 <= len(args.input) <= 8:
            raise IncidentReportComparisonError("reports_invalid")
        documents = [_read_json(path) for path in args.input]
        report = compare_incident_reports(documents)
        rendered = (json.dumps(report, ensure_ascii=False, indent=2) + "\n"
                    if args.format == "json" else render_markdown(report))
        if args.output:
            _write_new_file(args.output, rendered)
        else:
            sys.stdout.write(rendered)
        return 0
    except (ReportError, IncidentReportComparisonError) as exc:
        sys.stderr.write(f"compare_site_outage_reports: {exc.code}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
