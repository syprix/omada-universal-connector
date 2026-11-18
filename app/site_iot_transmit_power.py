"""Identity-redacted summary of IoT transmit-power inventory rows."""
from __future__ import annotations

from typing import Any


class SiteIotTransmitPowerError(ValueError):
    """Raised when the bounded transmit-power page has an invalid shape."""


_POWERS = {-20, -18, -15, -12, -10, -9, -6, -5, -3, 0, 1, 2, 3, 4, 5,
           14, 15, 16, 17, 18, 19, 20}
_CATEGORIES = {0: "disconnected", 1: "connected", 2: "pending",
               3: "heartbeat_missed", 4: "isolated"}
_ROW_FIELDS = {"mac", "name", "type", "model", "modelVersion", "status",
               "statusCategory", "ip", "override", "transmitPower"}


def project_site_iot_transmit_power(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteIotTransmitPowerError("response_invalid")
    missing = int("data" not in result)
    invalid = 0
    unknown = len(set(result) - {"totalRows", "currentPage", "currentSize", "data"})
    total_rows = result.get("totalRows")
    if total_rows is not None and (type(total_rows) is not int or not 0 <= total_rows < 2 ** 63):
        invalid += 1
        total_rows = None
    for key in ("currentPage", "currentSize"):
        value = result.get(key)
        if value is not None and (type(value) is not int or not 0 <= value < 2 ** 31):
            invalid += 1
    rows = result.get("data", [])
    if not isinstance(rows, list) or len(rows) > 100:
        raise SiteIotTransmitPowerError("response_invalid")
    power_counts: dict[int, int] = {}
    category_counts = {name: 0 for name in _CATEGORIES.values()}
    override_count = 0
    override_present_count = 0
    unknown += sum(len(set(row) - _ROW_FIELDS) for row in rows if isinstance(row, dict))
    for row in rows:
        if not isinstance(row, dict) or len(row) > len(_ROW_FIELDS) + 16:
            invalid += 1
            continue
        if "statusCategory" in row:
            value = row["statusCategory"]
            if type(value) is int and value in _CATEGORIES:
                category_counts[_CATEGORIES[value]] += 1
            else:
                invalid += 1
        if "transmitPower" in row:
            value = row["transmitPower"]
            if type(value) is int and value in _POWERS:
                power_counts[value] = power_counts.get(value, 0) + 1
            else:
                invalid += 1
        if "override" in row:
            value = row["override"]
            if type(value) is bool:
                override_present_count += 1
                override_count += int(value)
            else:
                invalid += 1
    observed = len(rows)
    data: dict[str, object] = {
        "observed_row_count": observed,
        "device_status_category_counts": category_counts,
        "transmit_power_device_counts_dbm": {str(k): v for k, v in sorted(power_counts.items())},
        "override_enabled_count": override_count,
        "override_value_present_count": override_present_count,
    }
    if total_rows is not None:
        data["total_row_count"] = total_rows
        data["more_rows_available"] = total_rows > observed
    for key, out in (("currentPage", "current_page"), ("currentSize", "page_size")):
        if type(result.get(key)) is int:
            data[out] = result[key]
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown or
                             (total_rows is not None and total_rows > observed))}
