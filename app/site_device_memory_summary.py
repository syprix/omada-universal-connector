"""Redacted memory-use summary for the fixed top-device ranking."""
from __future__ import annotations

from typing import Any


class SiteDeviceMemorySummaryError(ValueError):
    """Raised when the documented memory ranking exceeds its bounds."""


_FIELDS = {"name", "mac", "memUsage", "model", "modelVersion", "type"}


def project_site_device_memory_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > 100:
        raise SiteDeviceMemorySummaryError("ranked_devices_invalid")
    values: list[int] = []
    missing = invalid = unknown = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 8:
            invalid += 1
            continue
        unknown += len(set(row) - _FIELDS)
        value = row.get("memUsage")
        if type(value) is int and 0 <= value <= 100:
            values.append(value)
        elif "memUsage" not in row:
            missing += 1
        else:
            invalid += 1
    data: dict[str, object] = {"device_count": len(result)}
    if values:
        data["maximum_memory_usage_percent"] = max(values)
        data["average_memory_usage_percent"] = sum(values) / len(values)
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
