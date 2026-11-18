"""Redacted summary of application traffic in one category."""
from __future__ import annotations

import math
from typing import Any


class SiteCategoryApplicationSummaryError(ValueError):
    """Raised when the unpaged application list is malformed or oversized."""


_FIELDS = {
    "applicationName", "applicationId", "applicationDescription", "familyName",
    "familyId", "traffic", "trafficPercent", "block", "activeUser", "download",
    "upload", "clientsCount", "clients",
}
_MAX_ROWS = 1_000
_MAX_CLIENT_ROWS = 200
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


def project_site_category_application_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_ROWS:
        raise SiteCategoryApplicationSummaryError("response_invalid")
    totals = {"traffic": 0, "blocked": 0, "active_users": 0,
              "upload": 0, "download": 0, "clients": 0}
    complete = {key: True for key in totals}
    max_traffic: int | None = None
    max_share: float | None = None
    with_clients = invalid = unknown = missing = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 24:
            invalid += 1
            continue
        unknown += len(set(row) - _FIELDS)
        for key in ("applicationName", "applicationDescription", "familyName"):
            if key in row and not isinstance(row[key], str):
                invalid += 1
        for key in ("applicationId", "familyId"):
            if key in row and _integer(row[key], _INT32_MAX) is None:
                invalid += 1
        mapping = (("traffic", "traffic", _INT64_MAX),
                   ("block", "blocked", _INT64_MAX),
                   ("activeUser", "active_users", _INT32_MAX),
                   ("upload", "upload", _INT64_MAX),
                   ("download", "download", _INT64_MAX),
                   ("clientsCount", "clients", _INT32_MAX))
        for source, target, maximum in mapping:
            value = _integer(row.get(source), maximum) if source in row else None
            if value is None:
                if source in row:
                    invalid += 1
                else:
                    missing += 1
                complete[target] = False
            else:
                totals[target] += value
                if target == "traffic":
                    max_traffic = value if max_traffic is None else max(max_traffic, value)
        if "trafficPercent" in row:
            share = _percent(row["trafficPercent"])
            if share is None:
                invalid += 1
            else:
                max_share = share if max_share is None else max(max_share, share)
        else:
            missing += 1
        if "clients" in row:
            clients = row["clients"]
            if (not isinstance(clients, list) or len(clients) > _MAX_CLIENT_ROWS or
                    not all(isinstance(client, dict) for client in clients)):
                invalid += 1
            elif clients:
                with_clients += 1
        else:
            missing += 1
    data: dict[str, object] = {
        "application_count": len(result),
        "applications_with_client_rows": with_clients,
    }
    for key, output in (("traffic", "total_application_traffic_value"),
                        ("blocked", "block_event_count"),
                        ("active_users", "active_user_count"),
                        ("upload", "upload_traffic_value"),
                        ("download", "download_traffic_value"),
                        ("clients", "client_application_count")):
        data[output] = totals[key] if complete[key] else None
    if max_traffic is not None:
        data["maximum_application_traffic_value"] = max_traffic
    if max_share is not None:
        data["maximum_application_traffic_share_percent"] = max_share
    data.update({"missing_field_count": missing, "invalid_field_count": invalid,
                 "unknown_field_count": unknown})
    return {"data": data,
            "partial": bool(missing or invalid or unknown or any(not value for value in complete.values()))}
