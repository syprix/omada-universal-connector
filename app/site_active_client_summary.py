"""Redacted counts and traffic totals for the most-active client list."""
from __future__ import annotations

from typing import Any


class SiteActiveClientSummaryError(ValueError):
    """Raised when the unpaged active-client list is malformed or oversized."""


_FIELDS = {"name", "wireless", "type", "model", "mac", "totalTraffic"}
_MAX_ROWS = 1_000
_INT64_MAX = (1 << 63) - 1


def project_site_active_client_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_ROWS:
        raise SiteActiveClientSummaryError("response_invalid")
    wireless_count = 0
    wireless_complete = True
    total_traffic = 0
    traffic_complete = True
    maximum_traffic: int | None = None
    missing = invalid = unknown = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 12:
            invalid += 1
            wireless_complete = False
            traffic_complete = False
            continue
        unknown += len(set(row) - _FIELDS)
        for key in ("name", "type", "model", "mac"):
            if key in row and not isinstance(row[key], str):
                invalid += 1
        if "wireless" in row:
            if type(row["wireless"]) is bool:
                wireless_count += int(row["wireless"])
            else:
                invalid += 1
                wireless_complete = False
        else:
            missing += 1
            wireless_complete = False
        if "totalTraffic" in row:
            traffic = row["totalTraffic"]
            if type(traffic) is not int or not 0 <= traffic <= _INT64_MAX:
                invalid += 1
                traffic_complete = False
            else:
                total_traffic += traffic
                maximum_traffic = traffic if maximum_traffic is None else max(maximum_traffic, traffic)
        else:
            missing += 1
            traffic_complete = False
    data: dict[str, object] = {
        "client_count": len(result),
        "wireless_client_count": wireless_count if wireless_complete else None,
        "wired_client_count": len(result) - wireless_count if wireless_complete else None,
        "total_client_traffic_value": total_traffic if traffic_complete else None,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
    }
    if maximum_traffic is not None:
        data["maximum_client_traffic_value"] = maximum_traffic
    return {"data": data,
            "partial": bool(missing or invalid or unknown or not wireless_complete or not traffic_complete)}
