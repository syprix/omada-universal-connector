"""Bounded summaries for controller-wide known and unknown device rows."""
from __future__ import annotations

from typing import Any


MAX_PAGE_ROWS = 200
KNOWN_FIELDS = {
    "mac", "name", "type", "subtype", "deviceSeriesType", "model", "ip", "ipv6",
    "uptime", "status", "lastSeen", "cpuUtil", "memUtil", "sn", "licenseStatus",
    "needActive", "siteName", "tagName",
}
UNKNOWN_FIELDS = {
    "mac", "name", "type", "subtype", "deviceSeriesType", "model", "ip", "uptime",
    "status", "lastSeen",
}
_TYPE_ALIASES = {
    "ap": "access_point", "accesspoint": "access_point", "access_point": "access_point",
    "gateway": "gateway", "router": "gateway", "switch": "switch", "olt": "olt",
}
_STATUS_CODES = {0, 1, 2, 3, 4}
_SERIES_CODES = {0, 1}


class GlobalDeviceSummaryError(ValueError):
    """Raised when a global device page cannot be safely summarized."""


def project_global_device_summary(result: Any, *, kind: str, page_size: int) -> dict[str, object]:
    if kind not in {"known", "unknown"} or type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_ROWS:
        raise GlobalDeviceSummaryError("response_invalid")
    if not isinstance(result, dict):
        raise GlobalDeviceSummaryError("response_invalid")
    rows = result.get("data")
    total = result.get("totalRows")
    page = result.get("currentPage")
    size = result.get("currentSize")
    if (not isinstance(rows, list) or len(rows) > page_size or type(total) is not int or total < 0 or
            type(page) is not int or page != 1 or type(size) is not int or
            size not in (len(rows), page_size) or len(rows) > total):
        raise GlobalDeviceSummaryError("response_invalid")

    allowed_fields = KNOWN_FIELDS if kind == "known" else UNKNOWN_FIELDS
    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    series_counts: dict[str, int] = {}
    missing = invalid = unknown = unknown_values = 0
    for row in rows:
        if not isinstance(row, dict):
            invalid += 1
            continue
        unknown += len(set(row) - allowed_fields)

        device_type = row.get("type")
        if device_type is None:
            missing += 1
        elif isinstance(device_type, str) and device_type:
            normalized = _TYPE_ALIASES.get(device_type.strip().lower(), "other")
            type_counts[normalized] = type_counts.get(normalized, 0) + 1
            if normalized == "other":
                unknown_values += 1
        else:
            invalid += 1

        status = row.get("status")
        if status is None:
            missing += 1
        elif type(status) is int and status in _STATUS_CODES:
            key = str(status)
            status_counts[key] = status_counts.get(key, 0) + 1
        elif type(status) is int and 0 <= status <= 2_147_483_647:
            status_counts["unknown"] = status_counts.get("unknown", 0) + 1
            unknown_values += 1
        else:
            invalid += 1

        series = row.get("deviceSeriesType")
        if series is None:
            missing += 1
        elif type(series) is int and series in _SERIES_CODES:
            key = "basic" if series == 0 else "pro"
            series_counts[key] = series_counts.get(key, 0) + 1
        elif type(series) is int and 0 <= series <= 2_147_483_647:
            series_counts["unknown"] = series_counts.get("unknown", 0) + 1
            unknown_values += 1
        else:
            invalid += 1

    sampled = len(rows)
    return {
        "data": {
            "device_count": total,
            "sampled_count": sampled,
            "type_counts": type_counts,
            "status_code_counts": status_counts,
            "series_type_counts": series_counts,
            "missing_count": missing,
            "invalid_count": invalid,
            "unknown_field_count": unknown,
            "unknown_value_count": unknown_values,
        },
        "partial": bool(sampled < total or missing or invalid or unknown or unknown_values),
    }
