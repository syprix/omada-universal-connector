"""Redacted aggregate CPU utilization for the five busiest site devices."""
from __future__ import annotations

from typing import Any


class SiteCpuUsageSummaryError(ValueError):
    """Raised when the upstream CPU list is malformed or oversized."""


_FIELDS = {"name", "mac", "cpuUtil", "model", "modelVersion", "type"}
_MAX_ROWS = 5
_INT32_MAX = (1 << 31) - 1


def project_site_cpu_usage_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_ROWS:
        raise SiteCpuUsageSummaryError("response_invalid")
    total = 0
    minimum: int | None = None
    maximum: int | None = None
    complete = True
    missing = invalid = unknown = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 12:
            invalid += 1
            complete = False
            continue
        unknown += len(set(row) - _FIELDS)
        for key in ("name", "mac", "model", "modelVersion", "type"):
            if key in row and not isinstance(row[key], str):
                invalid += 1
        if "cpuUtil" not in row:
            missing += 1
            complete = False
            continue
        value = row["cpuUtil"]
        if type(value) is not int or not 0 <= value <= _INT32_MAX:
            invalid += 1
            complete = False
            continue
        total += value
        minimum = value if minimum is None else min(minimum, value)
        maximum = value if maximum is None else max(maximum, value)
    data: dict[str, object] = {
        "device_count": len(result),
        "mean_cpu_util_value": (total / len(result) if result and complete else None),
        "minimum_cpu_util_value": minimum if complete else None,
        "maximum_cpu_util_value": maximum if complete else None,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
    }
    return {"data": data,
            "partial": bool(missing or invalid or unknown or not complete)}
