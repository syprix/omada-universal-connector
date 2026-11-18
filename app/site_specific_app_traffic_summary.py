"""Aggregate app-specific client traffic without exposing client details."""
from __future__ import annotations

from typing import Any


class SiteSpecificAppTrafficSummaryError(ValueError):
    """Raised when the specific-app traffic response is malformed or too large."""


_FIELDS = {"type", "manager", "clientName", "mac", "traffic", "trafficPercent",
           "upload", "uploadTrafficPercent", "download", "downloadTrafficPercent",
           "totalApplications", "applicationList", "network", "vlanId"}
_MAX_CLIENT_ROWS = 1_000
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1


def project_site_specific_app_traffic_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_CLIENT_ROWS:
        raise SiteSpecificAppTrafficSummaryError("client_rows_invalid")
    missing = invalid = unknown = 0
    sums = {"traffic": 0, "upload": 0, "download": 0, "totalApplications": 0}
    complete = set(sums)
    for row in result:
        if not isinstance(row, dict) or len(row) > 24:
            invalid += 1
            complete.clear()
            continue
        unknown += len(set(row) - _FIELDS)
        for key in sums:
            if key not in row:
                missing += 1
                complete.discard(key)
                continue
            maximum = _INT64_MAX if key in {"traffic", "upload", "download"} else _INT32_MAX
            value = row[key]
            if type(value) is not int or not 0 <= value <= maximum:
                invalid += 1
                complete.discard(key)
            else:
                sums[key] += value
    data: dict[str, object] = {"client_row_count": len(result)}
    for key, label in (("traffic", "traffic_total"), ("upload", "upload_total"),
                       ("download", "download_total"),
                       ("totalApplications", "application_count_total")):
        data[label] = sums[key] if key in complete else None
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
