"""Bounded, identity-free summary for the top application traffic response."""
from __future__ import annotations

from typing import Any


class SiteApplicationTrafficSummaryError(ValueError):
    """Raised when the upstream top-traffic response exceeds its contract."""


_ROW_FIELDS = {"id", "name", "familyId", "familyName", "up", "down", "traffic"}
_LABEL_FIELDS = {"name", "familyName"}
_ID_FIELDS = {"id", "familyId"}
_INT64_MAX = (1 << 63) - 1
_INT32_MAX = (1 << 31) - 1
_MAX_ROWS = 10


def _counter(value: Any) -> bool:
    return type(value) is int and 0 <= value <= _INT64_MAX


def project_site_application_traffic_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_ROWS:
        raise SiteApplicationTrafficSummaryError("application_rows_invalid")

    totals = {"traffic": 0, "up": 0, "down": 0}
    complete = set(totals)
    missing = invalid = unknown = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 16:
            invalid += 1
            continue
        unknown += len(set(row) - _ROW_FIELDS)
        for key in _LABEL_FIELDS:
            if key in row and not isinstance(row[key], str):
                invalid += 1
        for key in _ID_FIELDS:
            if key in row and (type(row[key]) is not int or
                               not 0 <= row[key] <= _INT32_MAX):
                invalid += 1
        for key in totals:
            if key not in row:
                missing += 1
                complete.discard(key)
            elif not _counter(row[key]):
                invalid += 1
                complete.discard(key)
            else:
                totals[key] += row[key]

    return {
        "data": {
            "returned_application_count": len(result),
            "top_application_traffic_total": totals["traffic"] if "traffic" in complete else None,
            "top_application_upload_total": totals["up"] if "up" in complete else None,
            "top_application_download_total": totals["down"] if "down" in complete else None,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
