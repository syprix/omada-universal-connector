"""Aggregate the selected client's app traffic without exposing app details."""
from __future__ import annotations

from typing import Any


class SiteSpecificClientTrafficSummaryError(ValueError):
    """Raised when the specific-client response is malformed or too large."""


_FIELDS = {"applicationName", "applicationId", "applicationDescription", "familyName",
           "familyId", "traffic", "trafficPercent", "block", "activeUser", "download",
           "upload", "clientsCount", "clients"}
_MAX_APPLICATION_ROWS = 1_000
_INT64_MAX = (1 << 63) - 1


def project_site_specific_client_traffic_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_APPLICATION_ROWS:
        raise SiteSpecificClientTrafficSummaryError("application_rows_invalid")
    missing = invalid = unknown = 0
    sums = {"traffic": 0, "download": 0, "upload": 0}
    complete = set(sums)
    for row in result:
        if not isinstance(row, dict) or len(row) > 20:
            invalid += 1
            complete.clear()
            continue
        unknown += len(set(row) - _FIELDS)
        for key in sums:
            if key not in row:
                missing += 1
                complete.discard(key)
                continue
            value = row[key]
            if type(value) is not int or not 0 <= value <= _INT64_MAX:
                invalid += 1
                complete.discard(key)
            else:
                sums[key] += value
    data: dict[str, object] = {"application_row_count": len(result)}
    for key, label in (("traffic", "traffic_total"), ("download", "download_total"),
                       ("upload", "upload_total")):
        data[label] = sums[key] if key in complete else None
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
