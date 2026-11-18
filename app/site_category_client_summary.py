"""Redacted summary of client traffic in one application category."""
from __future__ import annotations

import math
from typing import Any


class SiteCategoryClientSummaryError(ValueError):
    """Raised when the unpaged client list is malformed or oversized."""


_FIELDS = {
    "type", "manager", "clientName", "mac", "traffic", "trafficPercent",
    "upload", "uploadTrafficPercent", "download", "downloadTrafficPercent",
    "totalApplications", "applicationList", "network", "vlanId",
}
_MAX_ROWS = 1_000
_MAX_APPLICATION_ROWS = 200
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


def project_site_category_client_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_ROWS:
        raise SiteCategoryClientSummaryError("response_invalid")
    totals = {"traffic": 0, "upload": 0, "download": 0, "applications": 0}
    complete = {key: True for key in totals}
    maximum_traffic: int | None = None
    maximum_share: float | None = None
    with_applications = missing = invalid = unknown = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 24:
            invalid += 1
            continue
        unknown += len(set(row) - _FIELDS)
        for key in ("type", "clientName", "mac", "network", "vlanId"):
            if key in row and not isinstance(row[key], str):
                invalid += 1
        if "manager" in row and type(row["manager"]) is not bool:
            invalid += 1
        for source, target, maximum in (("traffic", "traffic", _INT64_MAX),
                                        ("upload", "upload", _INT64_MAX),
                                        ("download", "download", _INT64_MAX),
                                        ("totalApplications", "applications", _INT32_MAX)):
            value = _integer(row[source], maximum) if source in row else None
            if value is None:
                if source in row:
                    invalid += 1
                else:
                    missing += 1
                complete[target] = False
            else:
                totals[target] += value
                if target == "traffic":
                    maximum_traffic = value if maximum_traffic is None else max(maximum_traffic, value)
        for key in ("trafficPercent", "uploadTrafficPercent", "downloadTrafficPercent"):
            if key in row:
                share = _percent(row[key])
                if share is None:
                    invalid += 1
                elif key == "trafficPercent":
                    maximum_share = share if maximum_share is None else max(maximum_share, share)
            else:
                missing += 1
        if "applicationList" in row:
            applications = row["applicationList"]
            if (not isinstance(applications, list) or len(applications) > _MAX_APPLICATION_ROWS or
                    not all(isinstance(app, dict) for app in applications)):
                invalid += 1
            elif applications:
                with_applications += 1
        else:
            missing += 1
    data: dict[str, object] = {
        "client_count": len(result),
        "clients_with_application_rows": with_applications,
        "total_client_traffic_value": totals["traffic"] if complete["traffic"] else None,
        "total_upload_traffic_value": totals["upload"] if complete["upload"] else None,
        "total_download_traffic_value": totals["download"] if complete["download"] else None,
        "total_application_count": totals["applications"] if complete["applications"] else None,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
    }
    if maximum_traffic is not None:
        data["maximum_client_traffic_value"] = maximum_traffic
    if maximum_share is not None:
        data["maximum_client_traffic_share_percent"] = maximum_share
    return {"data": data,
            "partial": bool(missing or invalid or unknown or any(not value for value in complete.values()))}
