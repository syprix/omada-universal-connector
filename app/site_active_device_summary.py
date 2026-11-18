"""Redacted activity totals for the fixed AP and switch rankings."""
from __future__ import annotations

import math
from typing import Any


class SiteActiveDeviceSummaryError(ValueError):
    """Raised when the documented ranked-device response exceeds bounds."""


_FIELDS = {"status", "name", "traffic", "mac", "model", "modelVersion"}


def _traffic_value(value: Any) -> float | None:
    if type(value) not in (int, float) or value < 0:
        return None
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return normalized if math.isfinite(normalized) else None


def project_site_active_device_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > 100:
        raise SiteActiveDeviceSummaryError("ranked_devices_invalid")
    connected = disconnected = missing = invalid = unknown = 0
    traffic: list[float] = []
    for row in result:
        if not isinstance(row, dict) or len(row) > 8:
            invalid += 1
            continue
        unknown += len(set(row) - _FIELDS)
        status = row.get("status")
        if type(status) is int and status in (0, 1):
            connected += int(status == 0)
            disconnected += int(status == 1)
        elif "status" not in row:
            missing += 1
        else:
            invalid += 1
        value = row.get("traffic")
        normalized = _traffic_value(value)
        if normalized is not None:
            traffic.append(normalized)
        elif "traffic" not in row:
            missing += 1
        else:
            invalid += 1
    data: dict[str, object] = {
        "device_count": len(result),
        "connected_device_count": connected,
        "disconnected_device_count": disconnected,
    }
    if traffic:
        data["maximum_device_traffic_value"] = max(traffic)
        try:
            total = math.fsum(traffic)
        except OverflowError:
            invalid += 1
        else:
            if math.isfinite(total):
                data["total_traffic_value"] = total
            else:
                invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
