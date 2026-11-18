"""Redacted wired-network dashboard totals for a fixed trailing day."""
from __future__ import annotations

from typing import Any


class SiteSwitchDashboardSummaryError(ValueError):
    """Raised when the documented switch dashboard response is invalid."""


_FIELDS = {"clients", "portUtilization", "connectedSwitchNum", "totalTraffic"}
_INT64_MAX = (1 << 63) - 1


def project_site_switch_dashboard_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteSwitchDashboardSummaryError("response_invalid")
    data: dict[str, object] = {}
    missing = invalid = 0
    unknown = len(set(result) - _FIELDS)
    for source, target in (
        ("clients", "wired_client_count"),
        ("connectedSwitchNum", "connected_switch_count"),
        ("portUtilization", "port_occupancy_value"),
        ("totalTraffic", "total_traffic_bytes"),
    ):
        if source not in result:
            missing += 1
            continue
        value = result[source]
        if type(value) is int and 0 <= value <= _INT64_MAX:
            data[target] = value
        else:
            invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
