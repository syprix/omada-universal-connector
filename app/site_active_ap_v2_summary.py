"""Redacted aggregate projection for the v2 active AP dashboard response."""
from __future__ import annotations

import math
from typing import Any

try:
    from .site_active_device_summary import (
        SiteActiveDeviceSummaryError, project_site_active_device_summary,
    )
except ImportError:  # direct execution in the image
    from site_active_device_summary import (
        SiteActiveDeviceSummaryError, project_site_active_device_summary,
    )


class SiteActiveApV2SummaryError(ValueError):
    """Raised when the v2 active AP response exceeds its documented bound."""


_FIELDS = {"activeAps", "totalTraffic"}
_MAX_APS = 10


def project_site_active_ap_v2_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise SiteActiveApV2SummaryError("response_invalid")
    unknown = len(set(result) - _FIELDS)
    missing = invalid = 0
    aps = result.get("activeAps")
    if not isinstance(aps, list) or len(aps) > _MAX_APS:
        raise SiteActiveApV2SummaryError("response_invalid")
    try:
        device_summary = project_site_active_device_summary(aps)
    except SiteActiveDeviceSummaryError:
        raise SiteActiveApV2SummaryError("response_invalid") from None

    if "totalTraffic" not in result:
        missing += 1
        reported_total = None
    else:
        value = result["totalTraffic"]
        try:
            numeric = float(value) if type(value) in (int, float) else float("nan")
        except (OverflowError, TypeError, ValueError):
            numeric = float("nan")
        if not math.isfinite(numeric) or numeric < 0:
            invalid += 1
            reported_total = None
        else:
            reported_total = numeric

    data = {
        "requested_device_count": _MAX_APS,
        "reported_total_traffic_value": reported_total,
        "active_ap_count": device_summary["data"]["device_count"],
        "connected_ap_count": device_summary["data"]["connected_device_count"],
        "disconnected_ap_count": device_summary["data"]["disconnected_device_count"],
        "maximum_ap_traffic_gb": device_summary["data"].get("maximum_device_traffic_value"),
    }
    missing += int(device_summary["missing_field_count"])
    invalid += int(device_summary["invalid_field_count"])
    unknown += int(device_summary["unknown_field_count"])
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown or device_summary["partial"])}
