"""Bounded projection for the documented site Bluetooth aging setting."""
from __future__ import annotations

from typing import Any


class SiteIotAgingTimeError(ValueError):
    """Raised when the documented aging-time object exceeds its contract."""


_FORMATS = {
    0: ("seconds", 30, 86_400),
    1: ("minutes", 1, 1_440),
    2: ("hours", 1, 24),
}


def project_site_iot_aging_time(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteIotAgingTimeError("response_invalid")
    fields = {"agingTime_iotAgingTime", "format_iotAgingTime"}
    missing = sum(name not in result for name in fields)
    unknown = len(set(result) - fields)
    invalid = 0
    value, unit = result.get("agingTime_iotAgingTime"), result.get("format_iotAgingTime")
    data: dict[str, object] = {}
    if type(value) is not int or type(unit) is not int or unit not in _FORMATS:
        invalid += int("agingTime_iotAgingTime" in result and type(value) is not int)
        invalid += int("format_iotAgingTime" in result and
                       (type(unit) is not int or unit not in _FORMATS))
        if type(value) is int and type(unit) is int and unit in _FORMATS:
            label, lower, upper = _FORMATS[unit]
            if lower <= value <= upper:
                data.update({"aging_value": value, "unit": label})
            else:
                invalid += 1
    else:
        label, lower, upper = _FORMATS[unit]
        if lower <= value <= upper:
            data.update({"aging_value": value, "unit": label})
        else:
            invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
