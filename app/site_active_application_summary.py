"""Redacted totals for the site's most-active application list."""
from __future__ import annotations

import math
from typing import Any


class SiteActiveApplicationSummaryError(ValueError):
    """Raised when the unpaged application list is malformed or oversized."""


_FIELDS = {"applicationName", "applicationId", "applicationDescription", "familyId",
           "familyName", "traffic", "trafficPercent", "clientsCount"}
_MAX_ROWS = 1_000
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1


def _integer(value: Any, maximum: int) -> int | None:
    if type(value) is int and 0 <= value <= maximum:
        return value
    return None


def _percent(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 100 else None


def project_site_active_application_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_ROWS:
        raise SiteActiveApplicationSummaryError("response_invalid")
    traffic_total = client_total = 0
    traffic_complete = client_complete = True
    max_traffic: int | None = None
    max_share: float | None = None
    missing = invalid = unknown = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 16:
            invalid += 1
            continue
        unknown += len(set(row) - _FIELDS)
        for key in ("applicationName", "applicationDescription", "familyName"):
            if key in row and not isinstance(row[key], str):
                invalid += 1
        for key in ("applicationId", "familyId"):
            if key in row and _integer(row[key], _INT32_MAX) is None:
                invalid += 1
        if "traffic" in row:
            value = _integer(row["traffic"], _INT64_MAX)
            if value is None:
                invalid += 1
                traffic_complete = False
            else:
                traffic_total += value
                max_traffic = value if max_traffic is None else max(max_traffic, value)
        else:
            missing += 1
            traffic_complete = False
        if "clientsCount" in row:
            value = _integer(row["clientsCount"], _INT32_MAX)
            if value is None:
                invalid += 1
                client_complete = False
            else:
                client_total += value
        else:
            missing += 1
            client_complete = False
        if "trafficPercent" in row:
            value = _percent(row["trafficPercent"])
            if value is None:
                invalid += 1
            else:
                max_share = value if max_share is None else max(max_share, value)
        else:
            missing += 1
    data: dict[str, object] = {
        "application_count": len(result),
        "total_application_traffic_value": traffic_total if traffic_complete else None,
        "total_client_application_count": client_total if client_complete else None,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
    }
    if max_traffic is not None:
        data["maximum_application_traffic_value"] = max_traffic
    if max_share is not None:
        data["maximum_application_traffic_share_percent"] = max_share
    return {"data": data,
            "partial": bool(missing or invalid or unknown or not traffic_complete or not client_complete)}
