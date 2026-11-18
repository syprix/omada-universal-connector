"""Identity-free totals for recent site network traffic and client counts."""
from __future__ import annotations

from typing import Any


class SiteNetworkActivitySummaryError(ValueError):
    """Raised when the site activity response exceeds its documented bounds."""


_COUNTS = {
    "totalTraffic": ("total_traffic", 2 ** 63 - 1),
    "totalUpload": ("total_upload_traffic", 2 ** 63 - 1),
    "totalDownload": ("total_download_traffic", 2 ** 63 - 1),
    "totalWiredCount": ("wired_client_count", 2 ** 31 - 1),
    "totalWirelessCount": ("wireless_client_count", 2 ** 31 - 1),
    "totalClientCount": ("total_client_count", 2 ** 31 - 1),
}
_FIELDS = set(_COUNTS) | {"existData", "activityList"}


def project_site_network_activity_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 12:
        raise SiteNetworkActivitySummaryError("response_invalid")
    missing = len((_FIELDS - {"activityList"}) - result.keys())
    invalid = 0
    unknown = len(set(result) - _FIELDS)
    data: dict[str, object] = {}
    for field, (output, upper) in _COUNTS.items():
        if field not in result:
            continue
        value = result[field]
        if type(value) is int and 0 <= value <= upper:
            data[output] = value
        else:
            invalid += 1
    if "existData" in result:
        if type(result["existData"]) is bool:
            data["data_available"] = result["existData"]
        else:
            invalid += 1
    activity = result.get("activityList")
    if "activityList" in result and (not isinstance(activity, list) or len(activity) > 10_000):
        invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
