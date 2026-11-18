"""Identity-free aggregate of site PoE use and rated capacity."""
from __future__ import annotations

from typing import Any


class SitePoeUsageSummaryError(ValueError):
    """Raised when the PoE usage response exceeds its documented bounds."""


_ROW_FIELDS = {"mac", "name", "portNum", "totalPowerUsed", "totalPercentUsed", "totalPower", "poePorts"}


def project_site_poe_usage_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > 500:
        raise SitePoeUsageSummaryError("response_invalid")
    invalid = 0
    unknown = 0
    used_sum = 0
    capacity_sum = 0
    port_sum = 0
    valid_used_count = 0
    valid_capacity_count = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > len(_ROW_FIELDS) + 8:
            invalid += 1
            continue
        unknown += len(set(row) - _ROW_FIELDS)
        for field, aggregate in (("totalPowerUsed", "used"), ("totalPower", "capacity")):
            if field not in row:
                continue
            value = row[field]
            if type(value) is not int or not 0 <= value < 2 ** 31:
                invalid += 1
            elif aggregate == "used":
                used_sum += value
                valid_used_count += 1
            else:
                capacity_sum += value
                valid_capacity_count += 1
        if "portNum" in row:
            value = row["portNum"]
            if type(value) is int and 0 <= value < 2 ** 31:
                port_sum += value
            else:
                invalid += 1
    data = {
        "switch_count": len(result),
        "reported_port_count": port_sum,
        "total_power_used_watts": used_sum,
        "rated_poe_capacity_watts": capacity_sum,
        "switches_with_power_usage_count": valid_used_count,
        "switches_with_capacity_count": valid_capacity_count,
    }
    return {"data": data, "missing_field_count": 0,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(invalid or unknown or valid_used_count < len(result)
                             or valid_capacity_count < len(result))}
