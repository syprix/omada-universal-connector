"""Redacted, page-bounded application-category traffic totals."""
from __future__ import annotations

import math
from typing import Any


class SiteApplicationCategorySummaryError(ValueError):
    """Raised when the documented category page exceeds its bounds."""


_ROOT_FIELDS = {"totalRows", "currentPage", "currentSize", "data", "stat"}
_ROW_FIELDS = {"familyId", "familyName", "traffic", "upload", "download",
               "trafficPercent", "totalApplications", "applications",
               "totalClients", "clients"}
_STAT_FIELDS = {"allowApps", "blockApps"}
_INT64_MAX = (1 << 63) - 1
_INT32_MAX = (1 << 31) - 1
_MAX_ROWS = 100
_MAX_NESTED_ROWS = 200


def _nonnegative_int(value: Any, maximum: int) -> int | None:
    if type(value) is int and 0 <= value <= maximum:
        return value
    return None


def _percentage(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 100 else None


def project_site_application_category_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteApplicationCategorySummaryError("response_invalid")
    data: dict[str, object] = {}
    missing = invalid = 0
    unknown = len(set(result) - _ROOT_FIELDS)
    total_rows = _nonnegative_int(result.get("totalRows"), _INT64_MAX)
    if total_rows is None:
        missing += int("totalRows" not in result)
        invalid += int("totalRows" in result)
    else:
        data["total_category_count"] = total_rows
    page = _nonnegative_int(result.get("currentPage"), _INT32_MAX)
    if page is None:
        missing += int("currentPage" not in result)
        invalid += int("currentPage" in result)
    else:
        data["reported_page"] = page
    page_size = _nonnegative_int(result.get("currentSize"), 100)
    if page_size is None:
        missing += int("currentSize" not in result)
        invalid += int("currentSize" in result)
    else:
        data["reported_page_size"] = page_size
    if "data" not in result:
        missing += 1
        rows: list[Any] = []
    else:
        rows = result["data"]
        if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
            raise SiteApplicationCategorySummaryError("category_rows_invalid")
    data["category_row_count"] = len(rows)
    traffic_values: list[int] = []
    shares: list[float] = []
    rows_with_apps = rows_with_clients = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 16:
            invalid += 1
            continue
        unknown += len(set(row) - _ROW_FIELDS)
        for key in ("familyId", "totalApplications", "totalClients"):
            if key in row:
                if _nonnegative_int(row[key], _INT32_MAX) is None:
                    invalid += 1
            else:
                missing += 1
        if "familyName" in row:
            if not isinstance(row["familyName"], str):
                invalid += 1
        else:
            missing += 1
        for key in ("upload", "download"):
            if key in row:
                if _nonnegative_int(row[key], _INT64_MAX) is None:
                    invalid += 1
            else:
                missing += 1
        for key, target in (("applications", "apps"), ("clients", "clients")):
            if key in row:
                if (isinstance(row[key], list) and
                        len(row[key]) <= _MAX_NESTED_ROWS and
                        all(isinstance(item, dict) for item in row[key])):
                    if row[key]:
                        if target == "apps":
                            rows_with_apps += 1
                        else:
                            rows_with_clients += 1
                else:
                    invalid += 1
            else:
                missing += 1
        for key, target in (("traffic", traffic_values),):
            if key in row:
                value = _nonnegative_int(row[key], _INT64_MAX)
                if value is None:
                    invalid += 1
                else:
                    target.append(value)
            else:
                missing += 1
        if "trafficPercent" in row:
            value = _percentage(row["trafficPercent"])
            if value is not None:
                shares.append(value)
            else:
                invalid += 1
        else:
            missing += 1
    data["category_rows_with_applications"] = rows_with_apps
    data["category_rows_with_clients"] = rows_with_clients
    if traffic_values:
        data["page_traffic_total_value"] = sum(traffic_values)
        data["maximum_category_traffic_value"] = max(traffic_values)
    if shares:
        data["maximum_category_traffic_share_percent"] = max(shares)
    has_more = total_rows is not None and total_rows > len(rows)
    if total_rows is not None and total_rows < len(rows):
        invalid += 1
    data["has_more_category_rows"] = has_more
    if has_more:
        data["unseen_category_row_count"] = total_rows - len(rows)
    if "stat" not in result:
        missing += 1
    else:
        stat = result["stat"]
        if not isinstance(stat, dict) or len(stat) > 4:
            invalid += 1
        else:
            unknown += len(set(stat) - _STAT_FIELDS)
            for key, target in (("allowApps", "allowed_application_count"),
                                ("blockApps", "blocked_application_count")):
                value = _nonnegative_int(stat.get(key), _INT32_MAX)
                if value is None:
                    missing += int(key not in stat)
                    invalid += int(key in stat)
                else:
                    data[target] = value
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown or has_more)}
