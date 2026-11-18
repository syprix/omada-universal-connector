from __future__ import annotations

from datetime import datetime, timezone


class SiteLogWindowError(ValueError):
    pass


MIN_TIME_MS = 946684800000  # 2000-01-01 UTC
MAX_TIME_MS = 4102444800000  # 2100-01-01 UTC
MAX_WINDOW_MS = 24 * 60 * 60 * 1000


def validate_site_log_window(start_ms: object, end_ms: object,
                             now_ms: int | None = None) -> tuple[int, int]:
    if (type(start_ms) is not int or type(end_ms) is not int or
            not MIN_TIME_MS <= start_ms <= MAX_TIME_MS or
            not MIN_TIME_MS <= end_ms <= MAX_TIME_MS or start_ms > end_ms or
            end_ms - start_ms > MAX_WINDOW_MS):
        raise SiteLogWindowError("time_window_invalid")
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if type(now_ms) is not int or end_ms > now_ms + 60_000:
        raise SiteLogWindowError("time_window_invalid")
    return start_ms, end_ms


def summarize_site_log_window(rows: object, kind: str, start_ms: int, end_ms: int,
                              total_count: int, module_totals: object = None
                              ) -> dict[str, object]:
    if (kind not in {"events", "alerts"} or not isinstance(rows, list) or
            len(rows) > 2_000 or type(total_count) is not int or total_count < len(rows) or
            type(start_ms) is not int or type(end_ms) is not int or start_ms > end_ms):
        raise SiteLogWindowError("log_window_invalid")
    modules = {"system", "device", "client"}
    module_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    timestamps: list[int] = []
    for row in rows:
        if not isinstance(row, dict):
            raise SiteLogWindowError("log_row_invalid")
        event_time = row.get("time")
        module = row.get("module")
        if (type(event_time) is not int or not start_ms <= event_time <= end_ms or
                not isinstance(module, str) or len(module) > 64):
            raise SiteLogWindowError("log_row_invalid")
        label = module.casefold()
        if label not in modules:
            label = "other"
        module_counts[label] = module_counts.get(label, 0) + 1
        timestamps.append(event_time)
        if kind == "alerts":
            severity = row.get("level")
            if not isinstance(severity, str) or len(severity) > 32:
                raise SiteLogWindowError("log_row_invalid")
            severity = severity.casefold()
            if severity not in {"info", "warning", "error", "critical"}:
                severity = "other"
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

    partial = len(rows) < total_count
    if module_totals is not None:
        if (kind != "events" or not isinstance(module_totals, dict) or
                set(module_totals) != modules or
                any(type(value) is not int or value < 0 for value in module_totals.values()) or
                sum(module_totals.values()) > total_count):
            raise SiteLogWindowError("log_summary_invalid")

    result: dict[str, object] = {
        "status": "ok", "resource": "site_" + kind + "_window_summary",
        "window_start_ms": start_ms, "window_end_ms": end_ms,
        "returned_count": len(rows), "total_count": total_count,
        "partial": partial, "module_counts": dict(sorted(module_counts.items())),
    }
    if timestamps:
        result["first_event_ms"] = min(timestamps)
        result["last_event_ms"] = max(timestamps)
    if module_totals is not None:
        result["controller_module_totals"] = dict(sorted(module_totals.items()))
    if kind == "alerts":
        result["severity_counts"] = dict(sorted(severity_counts.items()))
    return result
