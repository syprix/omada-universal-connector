"""Bounded, passcode-redacting projection for Bluetooth radio settings."""
from __future__ import annotations

import re
from typing import Any


class SiteIotRadioError(ValueError):
    """Raised when the radio settings object exceeds its documented bounds."""


_TX_POWER_DBM = {-20, -18, -15, -12, -10, -9, -6, -5, -3, 0, 1, 2, 3, 4,
                 5, 14, 15, 16, 17, 18, 19, 20}
_CONSOLE_MODES = {0: "auto", 1: "on", 2: "off"}
_AGING_FORMATS = {
    0: ("seconds", 30, 86_400),
    1: ("minutes", 1, 1_440),
    2: ("hours", 1, 24),
}
_FIELDS = {"enable", "consoleMode", "passcode", "transmitPower", "agingTime",
           "format", "resource"}


def project_site_iot_radio(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 16:
        raise SiteIotRadioError("response_invalid")
    missing = int("enable" not in result)
    invalid = 0
    unknown = len(set(result) - _FIELDS)
    data: dict[str, object] = {}

    enable = result.get("enable")
    if type(enable) is bool:
        data["bluetooth_enabled"] = enable
    elif "enable" in result:
        invalid += 1

    if "consoleMode" in result:
        value = result["consoleMode"]
        if type(value) is int and value in _CONSOLE_MODES:
            data["console_mode"] = _CONSOLE_MODES[value]
        else:
            invalid += 1

    if "passcode" in result:
        value = result["passcode"]
        if isinstance(value, str) and re.fullmatch(r"[0-9]{6}", value):
            data["passcode_configured"] = True
        else:
            invalid += 1

    if "transmitPower" in result:
        value = result["transmitPower"]
        if type(value) is int and value in _TX_POWER_DBM:
            data["transmit_power_dbm"] = value
        else:
            invalid += 1

    aging_fields = {"agingTime", "format"}
    present = aging_fields & result.keys()
    if present and present != aging_fields:
        missing += len(aging_fields - present)
    elif present:
        value, fmt = result["agingTime"], result["format"]
        if type(value) is int and type(fmt) is int and fmt in _AGING_FORMATS:
            unit, lower, upper = _AGING_FORMATS[fmt]
            if lower <= value <= upper:
                data.update({"aging_value": value, "aging_unit": unit})
            else:
                invalid += 1
        else:
            invalid += 1

    if "resource" in result:
        value = result["resource"]
        if type(value) is int and -(2 ** 31) <= value < 2 ** 31:
            data["resource_present"] = True
        else:
            invalid += 1

    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
