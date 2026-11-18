"""Identity-free aggregate of site device counts from the dashboard card."""
from __future__ import annotations

from typing import Any


class SiteDeviceCountsSummaryError(ValueError):
    """Raised when the site device-count response exceeds its schema bounds."""


_COUNTS = {
    "total": "total_device_count",
    "preConfig": "preconfigured_device_count",
    "connected": "connected_device_count",
    "disconnectedCount": "disconnected_device_count",
}


def project_site_device_counts_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > 100:
        raise SiteDeviceCountsSummaryError("response_invalid")
    sums = {output: 0 for output in _COUNTS.values()}
    present = {field: 0 for field in _COUNTS}
    invalid = 0
    unknown = 0
    missing = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 12:
            invalid += 1
            continue
        unknown += len(set(row) - (set(_COUNTS) | {"type"}))
        if "type" in row and (not isinstance(row["type"], str) or len(row["type"]) > 256):
            invalid += 1
        for field, output in _COUNTS.items():
            if field not in row:
                missing += 1
                continue
            value = row[field]
            if type(value) is int and 0 <= value < 2 ** 31:
                sums[output] += value
                present[field] += 1
            else:
                invalid += 1
    data: dict[str, object] = {"device_category_count": len(result), **sums}
    data["count_fields_present_by_category"] = {
        _COUNTS[field]: count for field, count in present.items()
    }
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
