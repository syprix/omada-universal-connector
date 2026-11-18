"""Small, validated projection for bounded controller threat windows."""
from __future__ import annotations


class ThreatWindowError(ValueError):
    """The source page or projected threat window is invalid."""


_SEVERITY_NAMES = {
    0: "critical",
    1: "major",
    2: "moderate",
    3: "minor",
    4: "low",
}


def summarize_threat_rows(rows: list[object], start_s: int, end_s: int,
                          total_rows: int, *, archived: bool,
                          max_items: int) -> dict[str, object]:
    if (type(start_s) is not int or type(end_s) is not int or
            start_s < 0 or end_s < start_s or type(total_rows) is not int or
            not 0 <= total_rows <= 1_000_000_000 or
            type(archived) is not bool or type(max_items) is not int or
            max_items <= 0 or len(rows) > max_items):
        raise ThreatWindowError("invalid threat window")

    counts: dict[str, int] = {name: 0 for name in _SEVERITY_NAMES.values()}
    unknown = 0
    first_time: int | None = None
    last_time: int | None = None
    for row in rows:
        if not isinstance(row, dict):
            raise ThreatWindowError("invalid threat row")
        timestamp = row.get("time")
        severity = row.get("severity")
        if (type(timestamp) is not int or not start_s <= timestamp <= end_s or
                type(severity) is not int or not 0 <= severity <= 2_147_483_647):
            raise ThreatWindowError("invalid threat fields")
        name = _SEVERITY_NAMES.get(severity)
        if name is None:
            unknown += 1
        else:
            counts[name] += 1
        first_time = timestamp if first_time is None else min(first_time, timestamp)
        last_time = timestamp if last_time is None else max(last_time, timestamp)

    partial = len(rows) < total_rows
    return {
        "status": "ok",
        "resource": "site_threat_window_summary",
        "archived": archived,
        "window_start_s": start_s,
        "window_end_s": end_s,
        "returned_rows": len(rows),
        "total_rows": total_rows,
        "counts": counts,
        "unknown_severity": unknown,
        "first_event_s": first_time,
        "last_event_s": last_time,
        "partial": partial,
    }
