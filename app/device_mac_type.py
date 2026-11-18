"""Validated projection for an inventoried device's MAC type check."""
from __future__ import annotations

from typing import Any

DEVICE_TYPES = {"ap", "switch", "gateway", "olt", "ipc", "nvr"}


class DeviceMacTypeError(ValueError):
    """Raised when the MAC type response is not a bounded object."""


def project_device_mac_type(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 2:
        raise DeviceMacTypeError("response_invalid")
    device: bool | None = None
    device_type: str | None = None
    invalid = 0
    if "device" in result:
        if type(result["device"]) is bool:
            device = result["device"]
        else:
            invalid += 1
    if "deviceType" in result:
        value = result["deviceType"]
        if isinstance(value, str) and value.casefold() in DEVICE_TYPES:
            device_type = value.casefold()
        else:
            invalid += 1
    known = {"device", "deviceType"}
    missing = len(known - result.keys())
    unknown = len(result.keys() - known)
    return {
        "data": {"is_device": device, "device_type": device_type,
                 "present_count": int(device is not None) + int(device_type is not None),
                 "missing_count": missing, "invalid_count": invalid,
                 "unknown_field_count": unknown},
        "partial": bool(missing or invalid or unknown),
    }
