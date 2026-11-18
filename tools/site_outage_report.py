#!/usr/bin/env python3
"""Create a redacted local Markdown or JSON report from an outage summary."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import stat
import sys


MAX_INPUT_BYTES = 256 * 1024
MAX_PATH_LENGTH = 4096
_DEVICE_CLASSES = ("access_points", "gateways", "switches")


class ReportError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_key")
        value[key] = item
    return value


def _reject_constant(_value: str) -> None:
    raise ValueError("invalid_constant")


def _read_json(path: str) -> object:
    if not isinstance(path, str) or not path or len(path) > MAX_PATH_LENGTH or not hasattr(os, "O_NOFOLLOW"):
        raise ReportError("input_invalid")
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                info.st_nlink != 1 or info.st_size > MAX_INPUT_BYTES or
                stat.S_IMODE(info.st_mode) & 0o077):
            raise ReportError("input_invalid")
        content = bytearray()
        while len(content) <= MAX_INPUT_BYTES:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        if len(content) > MAX_INPUT_BYTES:
            raise ReportError("input_invalid")
        return json.loads(bytes(content).decode("utf-8", errors="strict"),
                          object_pairs_hook=_pairs_no_duplicates,
                          parse_constant=_reject_constant)
    except ReportError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raise ReportError("input_invalid") from None
    finally:
        if fd >= 0:
            os.close(fd)


def _count(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        raise ReportError("summary_invalid")
    return value


def _date(value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not int or not 0 <= value <= 4_102_444_800_000:
        raise ReportError("summary_invalid")
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _project_reachability(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("status") not in {"ok", "unavailable"}:
        raise ReportError("summary_invalid")
    if value["status"] == "unavailable":
        return {"status": "unavailable"}
    raw_classes = value.get("device_classes")
    if not isinstance(raw_classes, dict) or set(raw_classes) != set(_DEVICE_CLASSES):
        raise ReportError("summary_invalid")
    classes: dict[str, object] = {}
    for name in _DEVICE_CLASSES:
        item = raw_classes[name]
        if not isinstance(item, dict) or set(item) != {"total", "connected", "disconnected"}:
            raise ReportError("summary_invalid")
        total, connected, disconnected = (_count(item.get(key)) for key in
                                          ("total", "connected", "disconnected"))
        if (type(total) is int and type(connected) is int and type(disconnected) is int and
                connected + disconnected > total):
            raise ReportError("summary_invalid")
        classes[name] = {"total": total, "connected": connected,
                          "disconnected": disconnected}
    isolated = _count(value.get("isolated_access_points"))
    if type(value.get("partial")) is not bool:
        raise ReportError("summary_invalid")
    return {"status": "partial" if value["partial"] else "ok",
            "device_classes": classes, "isolated_access_points": isolated,
            "missing_field_count": _count(value.get("missing_field_count"))}


def _project_log(value: object, *, alerts: bool) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("status") not in {"ok", "partial", "unavailable"}:
        raise ReportError("summary_invalid")
    if value["status"] == "unavailable":
        return {"status": "unavailable"}
    total, returned = _count(value.get("total_count")), _count(value.get("returned_count"))
    if total is None or returned is None or returned > total:
        raise ReportError("summary_invalid")
    modules = value.get("module_counts")
    if (not isinstance(modules, dict) or len(modules) > 8 or
            any(not isinstance(key, str) or len(key) > 32 or _count(count) is None
                for key, count in modules.items()) or sum(modules.values()) != returned):
        raise ReportError("summary_invalid")
    pagination = value.get("pagination")
    if not isinstance(pagination, dict):
        raise ReportError("summary_invalid")
    pages = pagination.get("pages_fetched")
    page_size = pagination.get("page_size")
    page_limit = pagination.get("page_limit")
    page_limit_reached = pagination.get("page_limit_reached")
    if (type(pages) is not int or pages < 0 or type(page_size) is not int or page_size < 1 or
            type(page_limit) is not int or page_limit < 1 or
            type(page_limit_reached) is not bool):
        raise ReportError("summary_invalid")
    result: dict[str, object] = {
        "status": value["status"], "total_count": total, "returned_count": returned,
        "module_counts": dict(modules),
        "pagination": {"pages_fetched": pages, "page_size": page_size,
                       "page_limit": page_limit, "page_limit_reached": page_limit_reached},
    }
    if alerts:
        severity = value.get("severity_counts")
        if (not isinstance(severity, dict) or len(severity) > 8 or
                any(not isinstance(key, str) or len(key) > 32 or _count(count) is None
                    for key, count in severity.items()) or
                sum(severity.values()) != returned):
            raise ReportError("summary_invalid")
        result["severity_counts"] = dict(severity)
    return result


def project_report(summary: object) -> dict[str, object]:
    if (not isinstance(summary, dict) or summary.get("resource") != "site_outage_summary" or
            summary.get("status") not in {"ok", "partial"} or
            type(summary.get("partial")) is not bool or
            summary["partial"] != (summary["status"] == "partial")):
        raise ReportError("summary_invalid")
    window = summary.get("window")
    sections = summary.get("sections")
    if (not isinstance(window, dict) or not isinstance(sections, dict) or
            set(sections) != {"current_reachability", "events", "alerts"}):
        raise ReportError("summary_invalid")
    start = _date(window.get("start_ms"))
    end = _date(window.get("end_ms"))
    if end < start:
        raise ReportError("summary_invalid")
    reachability = _project_reachability(sections["current_reachability"])
    events = _project_log(sections["events"], alerts=False)
    alerts = _project_log(sections["alerts"], alerts=True)
    observed = _date(summary.get("reachability_observed_at_ms"), optional=True)
    partial = (summary["partial"] or reachability["status"] != "ok" or
               events["status"] != "ok" or alerts["status"] != "ok")
    return {
        "report_schema_version": 1,
        "connector_version": "0.3.0-dev",
        "status": "partial" if partial else "ok",
        "window_utc": {"start": start, "end": end},
        "reachability_observed_at_utc": observed,
        "current_reachability": reachability,
        "events": events,
        "alerts": alerts,
        "scope_assessment": "indeterminate",
        "limitations": [
            "Reachability is a current snapshot, not a historical measurement for the selected window.",
            "Event and alert counts are not correlated to individual devices.",
            "No outage cause or site-wide outage is inferred.",
        ],
        "partial": partial,
        "sources": ["site_overview", "site_events_window_summary",
                    "site_alerts_window_summary"],
        "live_controller_tested": False,
    }


def render_markdown(report: dict[str, object]) -> str:
    window = report["window_utc"]
    reachability = report["current_reachability"]
    lines = ["# Site outage context", "", f"Status: **{report['status']}**",
             f"UTC window: {window['start']} to {window['end']}",
             f"Reachability snapshot: {report['reachability_observed_at_utc'] or 'unavailable'}",
             "", "## Current device reachability"]
    if reachability["status"] == "unavailable":
        lines.append("Snapshot unavailable.")
    else:
        for name, item in reachability["device_classes"].items():
            label = {"access_points": "Access points", "gateways": "Gateways",
                     "switches": "Switches"}[name]
            lines.append(f"- {label}: {item['connected']} connected / {item['total']} total; "
                         f"{item['disconnected']} disconnected")
        lines.append(f"- Isolated access points: {reachability['isolated_access_points']}")
    lines.extend(["", "## Events and alerts"])
    for name in ("events", "alerts"):
        item = report[name]
        if item["status"] == "unavailable":
            lines.append(f"- {name.title()}: unavailable")
        else:
            lines.append(f"- {name.title()}: {item['total_count']} total; "
                         f"{item['returned_count']} returned; "
                         f"{item['pagination']['pages_fetched']} pages fetched")
            if item["pagination"]["page_limit_reached"]:
                lines.append(f"  - {name.title()} pagination reached its configured limit.")
    lines.extend(["", "## Scope and limits", "Scope assessment: **indeterminate**."])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", "Sources: site overview, event window summary, alert window summary.",
                  "Live controller tested: no", ""])
    return "\n".join(lines)


def _write_new_file(path: str, content: str) -> None:
    if not path or len(path) > MAX_PATH_LENGTH or not hasattr(os, "O_NOFOLLOW"):
        raise ReportError("output_invalid")
    fd = -1
    created = False
    created_identity: tuple[int, int] | None = None
    success = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                     getattr(os, "O_CLOEXEC", 0), 0o600)
        created = True
        info = os.fstat(fd)
        created_identity = (info.st_dev, info.st_ino)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise ReportError("output_invalid")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            fd = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            success = True
    except ReportError:
        raise
    except OSError:
        raise ReportError("output_unavailable") from None
    finally:
        if fd >= 0:
            os.close(fd)
        if created and not success:
            try:
                info = os.stat(path, follow_symlinks=False)
                if (created_identity == (info.st_dev, info.st_ino) and
                        info.st_uid == os.geteuid() and stat.S_ISREG(info.st_mode) and
                        info.st_nlink == 1):
                    os.unlink(path)
            except OSError:
                pass


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        report = project_report(_read_json(args.input))
        content = (render_markdown(report) if args.format == "markdown" else
                   json.dumps(report, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), allow_nan=False) + "\n")
        if args.output:
            _write_new_file(args.output, content)
            print(json.dumps({"status": report["status"], "output": args.output},
                             separators=(",", ":")))
        else:
            sys.stdout.write(content)
        return 0 if report["status"] == "ok" else 1
    except ReportError as exc:
        print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2


if __name__ == "__main__":
    raise SystemExit(main())
