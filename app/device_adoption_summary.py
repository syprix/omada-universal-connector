"""Bounded, identity-free summaries for batch-adoptable and pending devices."""
from __future__ import annotations

from typing import Any


MAX_PAGE_ROWS = 200
_BATCH_FIELDS = {
    "type", "mac", "name", "model", "licenseStatus", "compatible", "inWhitelist",
    "statusCategory", "status", "hwVersion", "modelVersion", "omadacId",
    "wireless", "es", "deviceSeriesType",
}
_PENDING_FIELDS = {
    "mac", "name", "type", "subtype", "deviceSeriesType", "model", "modelName",
    "ip", "ipv6", "uptime", "status", "detailStatus", "modelVersion", "lastSeen",
    "cpuUtil", "memUtil", "sn", "licenseStatus", "tagName", "uplinkDeviceMac",
    "uplinkDeviceName", "uplinkDevicePort", "linkSpeed", "duplex", "switchConsistent",
    "publicIp", "firmwareVersion", "compatible", "active", "inWhiteList",
}
_TYPE_ALIASES = {
    "ap": "access_point", "accesspoint": "access_point", "access_point": "access_point",
    "access point": "access_point", "gateway": "gateway", "router": "gateway",
    "switch": "switch", "olt": "olt",
}
_CODE_FIELDS = {
    "status": "status_code_counts",
    "licenseStatus": "license_status_code_counts",
    "compatible": "compatible_code_counts",
    "statusCategory": "status_category_code_counts",
    "deviceSeriesType": "series_type_code_counts",
    "detailStatus": "detail_status_code_counts",
}
_BOOL_FIELDS = {
    "inWhitelist": "whitelist_counts", "inWhiteList": "whitelist_counts",
    "wireless": "wireless_counts", "es": "es_counts", "active": "active_counts",
}
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


class DeviceAdoptionSummaryError(ValueError):
    """Raised when an upstream adoption-device response has an unsafe shape."""


def summarize_adoption_devices(result: Any, *, kind: str, page_size: int) -> dict[str, object]:
    """Summarize one fixed page without returning device identity or descriptive data."""
    if kind not in {"batch", "pending"} or type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_ROWS:
        raise DeviceAdoptionSummaryError("response_invalid")

    if kind == "batch":
        if not isinstance(result, list) or len(result) > page_size:
            raise DeviceAdoptionSummaryError("response_invalid")
        rows = result
        total_rows: int | None = None
        page_truncated = len(rows) == page_size
        allowed = _BATCH_FIELDS
        expected_fields = ("type", "status", "licenseStatus", "compatible", "deviceSeriesType")
    else:
        if not isinstance(result, dict):
            raise DeviceAdoptionSummaryError("response_invalid")
        rows = result.get("data")
        total_rows = result.get("totalRows")
        current_page = result.get("currentPage")
        current_size = result.get("currentSize")
        if (not isinstance(rows, list) or len(rows) > page_size or type(total_rows) is not int or
                total_rows < len(rows) or total_rows > 2**63 - 1 or
                type(current_page) is not int or current_page != 1 or
                type(current_size) is not int or current_size not in (len(rows), page_size)):
            raise DeviceAdoptionSummaryError("response_invalid")
        page_truncated = len(rows) < total_rows
        allowed = _PENDING_FIELDS
        expected_fields = ("type", "status", "licenseStatus", "compatible", "deviceSeriesType")

    type_counts: dict[str, int] = {}
    code_counts: dict[str, dict[str, int]] = {name: {} for name in _CODE_FIELDS.values()}
    bool_counts: dict[str, dict[str, int]] = {
        name: {"true": 0, "false": 0} for name in dict.fromkeys(_BOOL_FIELDS.values())
    }
    missing = invalid = unknown = unknown_values = 0

    for row in rows:
        if not isinstance(row, dict):
            invalid += 1
            continue
        unknown += len(set(row) - allowed)
        for field in expected_fields:
            if field not in row or row[field] is None:
                missing += 1

        raw_type = row.get("type")
        if isinstance(raw_type, str) and raw_type.strip():
            value = _TYPE_ALIASES.get(raw_type.strip().casefold(), "other")
            type_counts[value] = type_counts.get(value, 0) + 1
            if value == "other":
                unknown_values += 1
        elif raw_type == "":
            missing += 1
        elif raw_type is not None:
            invalid += 1

        for field, output_name in _CODE_FIELDS.items():
            if field not in row or row[field] is None:
                continue
            value = row[field]
            if type(value) is int and _INT32_MIN <= value <= _INT32_MAX:
                code = str(value)
                bucket = code_counts[output_name]
                bucket[code] = bucket.get(code, 0) + 1
            else:
                invalid += 1

        for field, output_name in _BOOL_FIELDS.items():
            if field not in row or row[field] is None:
                continue
            value = row[field]
            if type(value) is bool:
                bucket = bool_counts[output_name]
                key = "true" if value else "false"
                bucket[key] += 1
            else:
                invalid += 1

    sampled = len(rows)
    data: dict[str, object] = {
        "sampled_count": sampled,
        "type_counts": type_counts,
        **code_counts,
        **bool_counts,
        "missing_count": missing,
        "invalid_count": invalid,
        "unknown_field_count": unknown,
        "unknown_value_count": unknown_values,
    }
    if total_rows is not None:
        data["device_count"] = total_rows
    return {
        "data": data,
        "partial": bool(page_truncated or missing or invalid or unknown or unknown_values),
    }
