from __future__ import annotations

from collections import Counter
from typing import Any

try:
    from .site_log_window_summary import SiteLogWindowError, validate_site_log_window
except ImportError:
    from site_log_window_summary import SiteLogWindowError, validate_site_log_window


_AUDIT_TYPES = {"Log", "Cloud Access", "User Interface"}
_LEVELS = {"Error", "Warning", "Information"}
_RESULTS = {"Succeed", "Failed"}
MAX_AUDIT_ROWS = 1_000


class AuditLogWindowError(ValueError):
    pass


def summarize_audit_log_window(rows: object, start_ms: int, end_ms: int,
                               total_count: int) -> dict[str, Any]:
    """Project only schema-backed fields safe for a compact audit timeline."""
    try:
        validate_site_log_window(start_ms, end_ms)
    except SiteLogWindowError:
        raise AuditLogWindowError("time_window_invalid") from None
    if (not isinstance(rows, list) or len(rows) > MAX_AUDIT_ROWS or
            type(total_count) is not int or total_count < len(rows) or total_count < 0):
        raise AuditLogWindowError("audit_rows_invalid")
    entries: list[dict[str, object]] = []
    type_counts: Counter[str] = Counter()
    level_counts: Counter[str] = Counter()
    result_counts: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise AuditLogWindowError("audit_row_invalid")
        timestamp = row.get("time")
        if type(timestamp) is not int or not start_ms <= timestamp <= end_ms:
            raise AuditLogWindowError("audit_row_invalid")
        audit_type = row.get("auditType")
        level = row.get("level")
        result = row.get("result")
        category = (audit_type if isinstance(audit_type, str) and
                    audit_type in _AUDIT_TYPES else "other")
        level_value = (level if isinstance(level, str) and level in _LEVELS else "other")
        result_value = (result if isinstance(result, str) and result in _RESULTS else "other")
        entries.append({"time_ms": timestamp, "category": category,
                        "level": level_value, "result": result_value})
        type_counts[category] += 1
        level_counts[level_value] += 1
        result_counts[result_value] += 1
    entries.sort(key=lambda entry: entry["time_ms"])
    return {
        "status": "ok",
        "resource": "audit_log_window_summary",
        "window_start_ms": start_ms,
        "window_end_ms": end_ms,
        "returned_count": len(entries),
        "total_count": total_count,
        "partial": len(entries) < total_count,
        "category_counts": dict(sorted(type_counts.items())),
        "level_counts": dict(sorted(level_counts.items())),
        "result_counts": dict(sorted(result_counts.items())),
        "entries": entries,
    }
