"""Summarize APs that the controller lists as eligible for interference scans."""
from __future__ import annotations

from collections.abc import Mapping


class SiteInterferenceScanEligibleError(ValueError):
    """The documented scan-capable AP list is malformed."""


_FIELDS = frozenset((
    "mac", "name", "model", "modelVersion", "type", "ip",
    "statusCategory", "status", "version", "addedInAdvanced",
    "uptimeLong", "wirelessLinked", "scanStatus", "powerModeList",
))
_STATUS_CATEGORIES = frozenset((0, 1, 2, 3, 4))
_STATUS_CODES = frozenset((
    0, 1, 10, 11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 25, 26, 27,
    30, 31, 32, 33, 40, 41, 50,
))
_SCAN_STATUSES = frozenset((0, 1, 2, 3, 4))
_POWER_MODES = frozenset((0, 1, 2))
_STRING_FIELDS = frozenset((
    "mac", "name", "model", "modelVersion", "type", "ip", "version",
))
MAX_ROWS = 500
PAGE = 1


def summarize_site_interference_scan_eligible_aps(value: object) -> dict[str, object]:
    page = 1
    page_size = MAX_ROWS
    total_rows: int | None = None
    if isinstance(value, dict):
        if set(value) - {"currentPage", "currentSize", "totalRows", "data"}:
            unknown_page_fields = len(set(value) - {"currentPage", "currentSize", "totalRows", "data"})
        else:
            unknown_page_fields = 0
        current_page = value.get("currentPage")
        current_size = value.get("currentSize")
        total = value.get("totalRows")
        rows_value = value.get("data")
        if (type(current_page) is not int or current_page < 1 or
                type(current_size) is not int or not 1 <= current_size <= MAX_ROWS or
                type(total) is not int or total < 0 or not isinstance(rows_value, list) or
                len(rows_value) > current_size):
            raise SiteInterferenceScanEligibleError("AP page is invalid")
        page, page_size, total_rows = current_page, current_size, total
        value = rows_value
    else:
        unknown_page_fields = 0
    if not isinstance(value, list):
        raise SiteInterferenceScanEligibleError("AP list must be a list")

    rows = value[:MAX_ROWS]
    scan_counts: dict[str, int] = {}
    power_counts: dict[str, int] = {}
    connected = wireless = 0
    valid = invalid = unknown = missing_scan_status = 0
    unknown_scan_status = unknown_power_mode = 0

    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 28:
            invalid += 1
            continue
        valid += 1
        unknown += sum(key not in _FIELDS for key in row)
        for key in _STRING_FIELDS:
            if key in row and not isinstance(row[key], str):
                invalid += 1

        for key, known, label, counts in (
                ("statusCategory", _STATUS_CATEGORIES, "category", None),
                ("status", _STATUS_CODES, "status", None),
                ("scanStatus", _SCAN_STATUSES, "scan", scan_counts)):
            if key not in row:
                if key == "scanStatus":
                    missing_scan_status += 1
                continue
            number = row[key]
            if isinstance(number, bool) or not isinstance(number, int):
                invalid += 1
                continue
            if number not in known:
                if label == "scan":
                    unknown_scan_status += 1
                else:
                    unknown += 1
                continue
            if counts is not None:
                k = str(number)
                counts[k] = counts.get(k, 0) + 1
            elif key == "statusCategory" and number == 1:
                connected += 1

        if "wirelessLinked" in row:
            if isinstance(row["wirelessLinked"], bool):
                wireless += int(row["wirelessLinked"])
            else:
                invalid += 1
        modes = row.get("powerModeList")
        if modes is not None:
            if not isinstance(modes, list) or len(modes) > 4:
                invalid += 1
            else:
                for mode in modes:
                    if isinstance(mode, bool) or not isinstance(mode, int):
                        invalid += 1
                    elif mode not in _POWER_MODES:
                        unknown_power_mode += 1
                    else:
                        key = str(mode)
                        power_counts[key] = power_counts.get(key, 0) + 1
        for key in ("addedInAdvanced",):
            if key in row and not isinstance(row[key], bool):
                invalid += 1
        if "uptimeLong" in row:
            uptime = row["uptimeLong"]
            if isinstance(uptime, bool) or not isinstance(uptime, int) or uptime < 0:
                invalid += 1

    truncated = len(value) > MAX_ROWS
    coverage_unknown = total_rows is None or total_rows > len(rows) or page != 1
    return {
        "data": {
            "returned_ap_count": len(value),
            "valid_ap_count": valid,
            "connected_ap_count": connected,
            "wireless_linked_ap_count": wireless,
            "scan_status_counts": scan_counts,
            "power_mode_counts": power_counts,
            "page": page,
            "page_size": page_size,
            "total_count": total_rows,
            "total_count_known": total_rows is not None,
            "coverage_scope": "first_page_only" if coverage_unknown else "complete_reported_page",
            "coverage_unknown": coverage_unknown,
            "truncated": truncated,
        },
        "missing_field_count": missing_scan_status,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown + unknown_scan_status + unknown_power_mode + unknown_page_fields,
        "partial": bool(invalid or unknown or missing_scan_status or
                        unknown_scan_status or unknown_power_mode or truncated or
                        unknown_page_fields or coverage_unknown),
    }
