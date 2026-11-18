"""Compact, identity-free summaries for dashboard allowed/blocked apps."""
from __future__ import annotations

from typing import Any


class SiteApplicationAccessSummaryError(ValueError):
    """Raised when the application dashboard response exceeds its contract bounds."""


_ROOT_FIELDS = {"totalRows", "currentPage", "currentSize", "data", "stat"}
_ROW_FIELDS = {"applicationName", "applicationId", "applicationDescription", "familyName",
               "familyId", "traffic", "trafficPercent", "block", "activeUser", "download",
               "upload", "clientsCount", "clients"}
_STAT_FIELDS = {"allowApps", "blockApps"}
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1
_MAX_ROWS = 100


def _count(value: Any, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def project_site_application_access_summary(result: Any, page_size: int | None = None) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 7:
        raise SiteApplicationAccessSummaryError("response_invalid")
    missing = invalid = 0
    unknown = len(set(result) - _ROOT_FIELDS)
    rows = result.get("data")
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise SiteApplicationAccessSummaryError("application_rows_invalid")

    totals = {"traffic": 0, "download": 0, "upload": 0,
              "activeUser": 0, "clientsCount": 0}
    complete = set(totals)
    for row in rows:
        if not isinstance(row, dict) or len(row) > 20:
            invalid += 1
            continue
        unknown += len(set(row) - _ROW_FIELDS)
        for key in totals:
            if key not in row:
                missing += 1
                complete.discard(key)
                continue
            maximum = _INT64_MAX if key in {"traffic", "download", "upload"} else _INT32_MAX
            if not _count(row[key], maximum):
                invalid += 1
                complete.discard(key)
            else:
                totals[key] += row[key]

    data: dict[str, object] = {
        "returned_application_count": len(rows),
        "page_traffic_total": totals["traffic"] if "traffic" in complete else None,
        "page_download_total": totals["download"] if "download" in complete else None,
        "page_upload_total": totals["upload"] if "upload" in complete else None,
        "page_active_user_total": totals["activeUser"] if "activeUser" in complete else None,
        "page_client_count_total": totals["clientsCount"] if "clientsCount" in complete else None,
    }
    for key in ("totalRows", "currentPage", "currentSize"):
        if key not in result:
            missing += 1
            continue
        if not _count(result[key], _INT32_MAX):
            invalid += 1
            continue
        label = {"totalRows": "total_rows", "currentPage": "current_page",
                 "currentSize": "current_page_size"}[key]
        data[label] = result[key]
    effective_page_size = page_size if page_size is not None else data.get("current_page_size")
    if ("total_rows" in data and "current_page" in data and
            type(effective_page_size) is int and effective_page_size > 0):
        data["has_more_pages"] = (
            data["current_page"] * effective_page_size < data["total_rows"])

    stat = result.get("stat")
    if not isinstance(stat, dict):
        missing += 1
        data["reported_allowed_application_total"] = None
        data["reported_blocked_application_total"] = None
    else:
        if len(stat) > 4:
            raise SiteApplicationAccessSummaryError("statistics_invalid")
        unknown += len(set(stat) - _STAT_FIELDS)
        for key, label in (("allowApps", "reported_allowed_application_total"),
                           ("blockApps", "reported_blocked_application_total")):
            value = stat.get(key)
            if key not in stat:
                missing += 1
                data[label] = None
            elif _count(value, _INT32_MAX):
                data[label] = value
            else:
                invalid += 1
                data[label] = None

    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
