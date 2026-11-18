"""Aggregate AP and switch traffic without returning device-level rows."""
from __future__ import annotations

import math
from typing import Any


class SiteDeviceTrafficSummaryError(ValueError):
    """Raised when the documented traffic response exceeds its bounds."""


_LISTS = {"aps": ("access_point", "ap_traffic_mb"),
          "switches": ("switch", "switch_traffic_mb")}


def _summarize(rows: Any) -> tuple[int, float, int, int]:
    if not isinstance(rows, list) or len(rows) > 1_000:
        raise SiteDeviceTrafficSummaryError("traffic_rows_invalid")
    total_values: list[float] = []
    invalid = unknown = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 8:
            invalid += 1
            continue
        unknown += len(set(row) - {"name", "mac", "traffic", "trafficProportion"})
        value = row.get("traffic")
        try:
            valid = type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e12
        except (OverflowError, TypeError):
            valid = False
        if valid:
            total_values.append(float(value))
        else:
            invalid += 1
    total = math.fsum(total_values)
    if not math.isfinite(total) or total > 1e15:
        raise SiteDeviceTrafficSummaryError("traffic_total_invalid")
    return len(rows), round(total, 3), invalid, unknown


def project_site_device_traffic_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise SiteDeviceTrafficSummaryError("response_invalid")
    data: dict[str, object] = {}
    missing = invalid = unknown = 0
    unknown = len(set(result) - set(_LISTS))
    for field, (prefix, output) in _LISTS.items():
        if field not in result:
            missing += 1
            continue
        count, total, bad, extras = _summarize(result[field])
        data[f"{prefix}_row_count"] = count
        data[output] = total
        invalid += bad
        unknown += extras
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
