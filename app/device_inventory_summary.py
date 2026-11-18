"""Aggregate the controller's unpaged device inventory without identities."""
from __future__ import annotations

from typing import Any

MAX_ROWS = 5_000
MAX_INT32 = 2**31 - 1
MIN_INT32 = -(2**31)
ROOT_FIELDS = {"data", "totalRows", "currentPage", "currentSize"}
ROW_FIELDS = {"deviceType", "type", "status"}


class DeviceInventorySummaryError(ValueError):
    """Raised when the all-devices response exceeds its bounded shape."""


def summarize_device_inventory(result: Any) -> dict[str, object]:
    if isinstance(result, list):
        rows = result
        root_unknown = 0
    elif isinstance(result, dict):
        if len(result) > 12:
            raise DeviceInventorySummaryError("response_invalid")
        rows = result.get("data")
        root_unknown = len(result.keys() - ROOT_FIELDS)
        total = result.get("totalRows")
        if total is not None:
            if type(total) is not int or not isinstance(rows, list) or total != len(rows):
                raise DeviceInventorySummaryError("response_invalid")
        current_page = result.get("currentPage")
        if current_page is not None and (type(current_page) is not int or current_page != 1):
            raise DeviceInventorySummaryError("response_invalid")
        current_size = result.get("currentSize")
        if current_size is not None and (type(current_size) is not int or not isinstance(rows, list) or current_size != len(rows)):
            raise DeviceInventorySummaryError("response_invalid")
    else:
        raise DeviceInventorySummaryError("response_invalid")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise DeviceInventorySummaryError("response_invalid")

    type_counts = {"access_point": 0, "gateway": 0, "switch": 0, "other": 0}
    status_counts: dict[int, int] = {}
    missing_type = missing_status = invalid = unknown = 0
    unknown += root_unknown
    for row in rows:
        if not isinstance(row, dict) or len(row) > 64:
            raise DeviceInventorySummaryError("response_invalid")
        unknown += len(row.keys() - ROW_FIELDS)
        raw_type = row.get("deviceType", row.get("type"))
        if raw_type is None:
            missing_type += 1
        elif not isinstance(raw_type, str) or len(raw_type) > 64:
            invalid += 1
        else:
            device_type = raw_type.strip().casefold()
            if device_type in {"ap", "access point", "accesspoint"}:
                type_counts["access_point"] += 1
            elif device_type in {"gateway", "router", "gw"}:
                type_counts["gateway"] += 1
            elif device_type in {"switch", "sw"}:
                type_counts["switch"] += 1
            else:
                type_counts["other"] += 1
        status = row.get("status")
        if status is None:
            missing_status += 1
        elif type(status) is not int or not MIN_INT32 <= status <= MAX_INT32:
            invalid += 1
        else:
            status_counts[status] = status_counts.get(status, 0) + 1

    complete = not (missing_type or missing_status or invalid or unknown)
    return {
        "data": {
            "device_count": len(rows),
            "type_counts": type_counts,
            "status_counts": [{"code": code, "count": status_counts[code]}
                              for code in sorted(status_counts)],
            "missing_type_count": missing_type,
            "missing_status_count": missing_status,
            "invalid_count": invalid,
            "unknown_field_count": unknown,
        },
        "partial": not complete,
    }
