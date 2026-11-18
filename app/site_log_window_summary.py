from __future__ import annotations

from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class SiteLogWindowError(ValueError):
    pass


MIN_TIME_MS = 946684800000  # 2000-01-01 UTC
MAX_TIME_MS = 4102444800000  # 2100-01-01 UTC
MAX_WINDOW_MS = 24 * 60 * 60 * 1000
_LOCAL_DATETIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,3})?)?"
)
_TIME_ZONE = re.compile(r"[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*")


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


def resolve_local_site_log_window(start_local: object, end_local: object,
                                  time_zone: object, now_ms: int | None = None
                                  ) -> tuple[int, int, str, datetime, datetime]:
    """Resolve naive local wall times through an explicit IANA timezone.

    Ambiguous and nonexistent wall times are rejected so DST transitions never
    silently select an offset. The upstream API receives only UTC epoch ms.
    """
    if (not isinstance(start_local, str) or not isinstance(end_local, str) or
            not _LOCAL_DATETIME.fullmatch(start_local) or
            not _LOCAL_DATETIME.fullmatch(end_local) or
            not isinstance(time_zone, str) or len(time_zone) > 64 or
            not _TIME_ZONE.fullmatch(time_zone)):
        raise SiteLogWindowError("time_window_invalid")
    try:
        zone = ZoneInfo(time_zone)
        start_wall = datetime.fromisoformat(start_local)
        end_wall = datetime.fromisoformat(end_local)
    except (ValueError, ZoneInfoNotFoundError):
        raise SiteLogWindowError("time_window_invalid") from None
    if start_wall.tzinfo is not None or end_wall.tzinfo is not None:
        raise SiteLogWindowError("time_window_invalid")

    def resolve(wall: datetime) -> datetime:
        first = wall.replace(tzinfo=zone, fold=0)
        second = wall.replace(tzinfo=zone, fold=1)
        if first.utcoffset() != second.utcoffset():
            raise SiteLogWindowError("time_window_invalid")
        utc_value = first.astimezone(timezone.utc)
        if utc_value.astimezone(zone).replace(tzinfo=None) != wall:
            raise SiteLogWindowError("time_window_invalid")
        return first

    start_aware, end_aware = resolve(start_wall), resolve(end_wall)
    start_ms = int(start_aware.astimezone(timezone.utc).timestamp() * 1000)
    end_ms = int(end_aware.astimezone(timezone.utc).timestamp() * 1000)
    start_ms, end_ms = validate_site_log_window(start_ms, end_ms, now_ms)
    return start_ms, end_ms, time_zone, start_aware, end_aware


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
