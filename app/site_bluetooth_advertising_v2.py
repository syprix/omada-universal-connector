"""Identity-redacted summary for the fixed Bluetooth Advertising v2 page."""
from __future__ import annotations

from typing import Any


class SiteBluetoothAdvertisingV2Error(ValueError):
    """Raised when the bounded Bluetooth Advertising v2 response is malformed."""


_INT32_FIELDS = {
    "transmitPower", "measurePower", "advInterval", "buildIn",
}
_STRING_FIELDS = {"id", "name", "uuid", "major", "minor"}
_ARRAY_FIELDS = {"macList", "selectMacInfo"}
_FIELDS = _INT32_FIELDS | _STRING_FIELDS | _ARRAY_FIELDS | {"boundDeviceNum", "enable"}
_GRID_FIELDS = {"totalRows", "currentPage", "currentSize", "data"}
_MAX_INT32 = 2 ** 31
_MIN_INT32 = -(2 ** 31)


def _valid_int32(value: Any) -> bool:
    return type(value) is int and _MIN_INT32 <= value < _MAX_INT32


def _valid_int64(value: Any) -> bool:
    return type(value) is int and -(2 ** 63) <= value < 2 ** 63


def project_site_bluetooth_advertising_v2(result: Any) -> dict[str, object]:
    """Project at most one page without retaining or returning beacon identifiers."""
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteBluetoothAdvertisingV2Error("response_invalid")

    missing = sum(key not in result for key in _GRID_FIELDS)
    invalid = 0
    unknown = len(set(result) - _GRID_FIELDS)
    total_rows = result.get("totalRows")
    current_page = result.get("currentPage")
    current_size = result.get("currentSize")
    if "totalRows" in result and (
        not _valid_int64(result["totalRows"]) or result["totalRows"] < 0
    ):
        invalid += 1
        total_rows = None
    if "currentPage" in result and (not _valid_int32(current_page) or current_page != 1):
        raise SiteBluetoothAdvertisingV2Error("response_invalid")
    rows = result.get("data", [])
    if not isinstance(rows, list) or len(rows) > 100:
        raise SiteBluetoothAdvertisingV2Error("response_invalid")
    if "currentSize" in result and (
        not _valid_int32(current_size) or current_size not in (len(rows), 100)
    ):
        raise SiteBluetoothAdvertisingV2Error("response_invalid")
    if total_rows is not None and total_rows < len(rows):
        raise SiteBluetoothAdvertisingV2Error("response_invalid")

    enabled = disabled = enable_missing = enable_invalid = 0
    bound_present = bound_valid = bound_missing = bound_invalid = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > len(_FIELDS) + 16:
            invalid += 1
            continue
        unknown += len(set(row) - _FIELDS)
        for field in _FIELDS:
            if field not in row:
                missing += 1
        # Validate documented types without retaining or exposing their values.
        for field in _INT32_FIELDS & row.keys():
            value = row[field]
            if not _valid_int32(value):
                invalid += 1
        for field in _STRING_FIELDS & row.keys():
            if not isinstance(row[field], str):
                invalid += 1
        if "macList" in row:
            value = row["macList"]
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                invalid += 1
        if "selectMacInfo" in row:
            value = row["selectMacInfo"]
            if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                invalid += 1
        if "enable" not in row:
            enable_missing += 1
        elif type(row["enable"]) is not bool:
            enable_invalid += 1
            invalid += 1
        elif row["enable"]:
            enabled += 1
        else:
            disabled += 1
        if "boundDeviceNum" not in row:
            bound_missing += 1
        else:
            bound_present += 1
            value = row["boundDeviceNum"]
            if _valid_int32(value) and value >= 0:
                bound_valid += 1
            else:
                bound_invalid += 1
                invalid += 1

    observed = len(rows)
    incomplete = total_rows is None or total_rows > observed
    data: dict[str, object] = {
        "observed_row_count": observed,
        "enabled_count": enabled,
        "disabled_count": disabled,
        "enable_missing_count": enable_missing,
        "enable_invalid_count": enable_invalid,
        "bound_device_count_present_rows": bound_present,
        "bound_device_count_valid_rows": bound_valid,
        "bound_device_count_missing_rows": bound_missing,
        "bound_device_count_invalid_rows": bound_invalid,
    }
    if total_rows is not None:
        data["total_row_count"] = total_rows
    if type(current_page) is int:
        data["current_page"] = current_page
    if type(current_size) is int:
        data["reported_page_size"] = current_size
    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or incomplete),
    }
