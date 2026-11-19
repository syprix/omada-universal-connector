"""Compare compact, already-redacted site outage reports without live reads."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from collections.abc import Mapping

MAX_REPORTS = 8
MAX_INPUT_BYTES = 60 * 1024
_REPORT_FIELDS = frozenset({
    "report_schema_version", "connector_version", "status", "window_utc",
    "reachability_observed_at_utc", "current_reachability", "events", "alerts",
    "scope_assessment", "limitations", "partial", "sources", "live_controller_tested",
})
_DEVICE_CLASSES = ("access_points", "gateways", "switches")


class IncidentReportComparisonError(ValueError):
    """The caller did not provide a bounded report collection."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _time(value: object) -> tuple[str, int] | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        utc = parsed.astimezone(timezone.utc)
        return utc.isoformat().replace("+00:00", "Z"), int(utc.timestamp() * 1000)
    except (ValueError, OverflowError, OSError):
        return None


def _integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= 1_000_000_000


def _known_report(value: object, index: int) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 64:
        raise IncidentReportComparisonError("report_invalid")
    if value.get("report_schema_version") != 1 or type(value.get("report_schema_version")) is not int:
        return {"report_index": index, "source_status": "unsupported",
                "reason": "source_or_schema_unsupported", "partial": True}

    window = value.get("window_utc")
    start = _time(window.get("start")) if isinstance(window, Mapping) else None
    end = _time(window.get("end")) if isinstance(window, Mapping) else None
    window_valid = (start is not None and end is not None and start[1] <= end[1])
    observed = _time(value.get("reachability_observed_at_utc"))
    report_status = value.get("status")
    report_partial = value.get("partial")
    if (not isinstance(report_status, str) or report_status not in {"ok", "partial"} or
            type(report_partial) is not bool):
        report_partial = True

    unknown_fields = sum(key not in _REPORT_FIELDS for key in value)
    reachability = value.get("current_reachability")
    reachability_status = (reachability.get("status")
                           if isinstance(reachability, Mapping) else None)
    device_counts: dict[str, dict[str, int]] = {}
    reachability_missing = 0
    isolated_count: int | None = None
    if (isinstance(reachability_status, str) and
            reachability_status in {"ok", "partial"} and isinstance(reachability, Mapping)):
        unknown_fields += sum(key not in {"status", "device_classes",
                                           "isolated_access_points", "missing_field_count",
                                           "partial"} for key in reachability)
        source_missing = reachability.get("missing_field_count", 0)
        if not _integer(source_missing):
            reachability_missing += 1
            source_missing = 0
        reachability_missing += source_missing
        if _integer(reachability.get("isolated_access_points")):
            isolated_count = reachability["isolated_access_points"]
        elif "isolated_access_points" in reachability:
            reachability_missing += 1
        classes = reachability.get("device_classes")
        if not isinstance(classes, Mapping):
            reachability_status = "unavailable"
            reachability_missing = 1
        else:
            unknown_fields += sum(name not in set(_DEVICE_CLASSES) for name in classes)
            for name in _DEVICE_CLASSES:
                row = classes.get(name)
                if (isinstance(row, Mapping) and all(_integer(row.get(key)) for key in
                        ("total", "connected", "disconnected")) and
                        row["connected"] + row["disconnected"] <= row["total"]):
                    unknown_fields += sum(key not in {"total", "connected", "disconnected"}
                                          for key in row)
                    device_counts[name] = {key: row[key] for key in
                                           ("total", "connected", "disconnected")}
                else:
                    reachability_missing += 1
    elif reachability_status != "unavailable":
        reachability_status = "unavailable"
        reachability_missing = 1

    metrics: dict[str, dict[str, object]] = {}
    pagination_limited: dict[str, bool | None] = {}
    for section_name in ("events", "alerts"):
        section = value.get(section_name)
        section_status = section.get("status") if isinstance(section, Mapping) else None
        if (not isinstance(section, Mapping) or not isinstance(section_status, str) or
                section_status not in {"ok", "partial"}):
            metrics[section_name] = {"status": "unavailable"}
            pagination_limited[section_name] = None
            continue
        total = section.get("total_count")
        returned = section.get("returned_count")
        unknown_fields += sum(key not in {"status", "total_count", "returned_count",
                                          "module_counts", "severity_counts",
                                          "pagination", "partial"} for key in section)
        pagination = section.get("pagination")
        limited = pagination.get("page_limit_reached") if isinstance(pagination, Mapping) else None
        if type(limited) is not bool:
            limited = None
        if isinstance(pagination, Mapping):
            unknown_fields += sum(key not in {"pages_fetched", "page_size", "page_limit",
                                              "page_limit_reached"} for key in pagination)
        pagination_limited[section_name] = limited
        valid = _integer(total) and _integer(returned) and returned <= total
        metrics[section_name] = ({"status": section_status,
                                 "total_count": total, "returned_count": returned}
                                if valid else {"status": "invalid_or_unavailable"})

    missing_sections = reachability_missing + sum(
        metrics[name]["status"] in {"unavailable", "invalid_or_unavailable"}
        for name in ("events", "alerts"))
    time_gaps = (int(start is None) + int(end is None) + int(observed is None) +
                 int(start is not None and end is not None and start[1] > end[1]))
    partial = (report_status != "ok" or report_partial is not False or
               time_gaps > 0 or
               reachability_status != "ok" or missing_sections > 0 or unknown_fields > 0 or
               any(metrics[name]["status"] != "ok" for name in ("events", "alerts")) or
               any(value is not False for value in pagination_limited.values()))
    return {
        "report_index": index,
        "source_status": "site_outage_report_v1",
        "status": "partial" if partial else "ok",
        "window_utc": {"start": start[0], "end": end[0]} if window_valid else None,
        "window_duration_ms": end[1] - start[1] if window_valid else None,
        "reachability_observed_at_utc": observed[0] if observed else None,
        "current_reachability": {"status": reachability_status,
                                 "device_classes": device_counts,
                                 "isolated_access_points": isolated_count},
        "events": metrics["events"],
        "alerts": metrics["alerts"],
        "pagination_limit_reached": pagination_limited,
        "missing_section_count": missing_sections,
        "time_gap_count": time_gaps,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "_window_ms": (start[1], end[1]) if window_valid else None,
        "_observed_ms": observed[1] if observed else None,
    }


def _compare_metric(reports: list[dict[str, object]], name: str, *, snapshot: bool = False
                    ) -> dict[str, object]:
    if any(row["source_status"] != "site_outage_report_v1" for row in reports):
        return {"metric": name, "status": "not_comparable_source", "values": []}
    windows = [row["_window_ms"] for row in reports]
    if any(window is None for window in windows):
        return {"metric": name, "status": "window_unavailable", "values": []}
    if snapshot:
        times = [row["_observed_ms"] for row in reports]
        if any(value is None for value in times):
            return {"metric": name, "status": "snapshot_time_unavailable", "values": []}
        if len(set(times)) != 1:
            return {"metric": name, "status": "snapshot_time_mismatch", "values": []}
    elif len(set(windows)) != 1:
        return {"metric": name, "status": "window_mismatch", "values": []}

    values: list[dict[str, int]] = []
    for row in reports:
        if row["partial"]:
            return {"metric": name, "status": "partial_source", "values": []}
        if snapshot:
            classes = row["current_reachability"]["device_classes"]
            if name == "current_reachability.disconnected_count" and len(classes) != len(_DEVICE_CLASSES):
                return {"metric": name, "status": "metric_unavailable", "values": []}
            if name == "current_reachability.isolated_access_points":
                value = row["current_reachability"]["isolated_access_points"]
                if not _integer(value):
                    return {"metric": name, "status": "metric_unavailable", "values": []}
            else:
                value = sum(classes[device]["disconnected"] for device in _DEVICE_CLASSES)
        else:
            section = row[name]
            if section.get("status") != "ok" or not _integer(section.get("total_count")):
                return {"metric": name, "status": "metric_unavailable", "values": []}
            value = section["total_count"]
        values.append({"report_index": row["report_index"], "value": value})
    return {"metric": name, "status": "comparable", "values": values,
            "delta_from_first": [
                {"report_index": row["report_index"], "delta": row["value"] - values[0]["value"]}
                for row in values[1:]
            ]}


def compare_incident_reports(reports: object) -> dict[str, object]:
    """Compare a bounded list of existing redacted site-outage report documents."""
    if not isinstance(reports, list) or not 2 <= len(reports) <= MAX_REPORTS:
        raise IncidentReportComparisonError("reports_invalid")
    try:
        size = len(json.dumps(reports, ensure_ascii=False, separators=(",", ":"),
                              allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise IncidentReportComparisonError("reports_invalid") from None
    if size > MAX_INPUT_BYTES:
        raise IncidentReportComparisonError("reports_too_large")
    summaries = [_known_report(value, index) for index, value in enumerate(reports, 1)]
    supported = [row for row in summaries if row["source_status"] == "site_outage_report_v1"]
    windows = [row["_window_ms"] for row in supported if row["_window_ms"] is not None]
    common_window = None
    if len(supported) == len(reports) and len(windows) == len(supported) and windows:
        start, end = max(window[0] for window in windows), min(window[1] for window in windows)
        if start <= end:
            common_window = {"start": datetime.fromtimestamp(start / 1000, timezone.utc)
                             .isoformat().replace("+00:00", "Z"),
                             "end": datetime.fromtimestamp(end / 1000, timezone.utc)
                             .isoformat().replace("+00:00", "Z")}
    comparisons = [
        _compare_metric(summaries, "events"),
        _compare_metric(summaries, "alerts"),
        _compare_metric(summaries, "current_reachability.disconnected_count", snapshot=True),
        _compare_metric(summaries, "current_reachability.isolated_access_points", snapshot=True),
    ]
    public_rows = [{key: value for key, value in row.items() if not key.startswith("_")}
                   for row in summaries]
    return {
        "status": "ok",
        "resource": "incident_report_comparison",
        "report_count": len(reports),
        "supported_report_count": len(supported),
        "unsupported_report_count": len(reports) - len(supported),
        "common_time_window_utc": common_window,
        "reports": public_rows,
        "comparisons": comparisons,
        "partial": any(row["partial"] for row in summaries) or len(supported) != len(reports),
        "live_controller_queries": 0,
        "limitations": [
            "Only site_outage_report schema version 1 is compared.",
            "Event and alert totals are comparable only for identical windows and complete reports.",
            "Current reachability snapshots are compared only when their observation times match exactly.",
            "A report comparison does not establish cause, correlation, or complete incident coverage.",
        ],
    }
