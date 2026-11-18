"""Redacted projection for a device adoption result."""
from __future__ import annotations

from typing import Any

FIELDS = {"deviceMac", "adoptErrorCode", "adoptFailedType"}
FAILURE_TYPES = {-1, -2}
ERROR_CODES = {0, -39002, -39003, -39004, -39005, -39329}


class DeviceAdoptResultError(ValueError):
    """Raised when an adoption result has an invalid shape."""


def project_device_adopt_result(result: Any, expected_mac: str) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > len(FIELDS):
        raise DeviceAdoptResultError("response_invalid")
    invalid = 0
    device_mac_present = False
    code: int | None = None
    credentials_required: bool | None = None
    if "deviceMac" in result:
        mac = result["deviceMac"]
        normalize = lambda value: value.replace(":", "").replace("-", "").casefold()
        if (not isinstance(mac, str) or not isinstance(expected_mac, str) or
                normalize(mac) != normalize(expected_mac)):
            invalid += 1
        else:
            device_mac_present = True
    if "adoptErrorCode" in result:
        value = result["adoptErrorCode"]
        if type(value) is int and value in ERROR_CODES:
            code = value
        else:
            invalid += 1
    if "adoptFailedType" in result:
        value = result["adoptFailedType"]
        if type(value) is int and value in FAILURE_TYPES:
            credentials_required = value == -2
        else:
            invalid += 1
    missing = len(FIELDS - result.keys())
    unknown = len(result.keys() - FIELDS)
    return {
        "data": {"adopt_error_code": code,
                 "credentials_required": credentials_required,
                 "present_count": int(device_mac_present) +
                                  int(code is not None) + int(credentials_required is not None),
                 "missing_count": missing, "invalid_count": invalid,
                 "unknown_field_count": unknown},
        "partial": bool(missing or invalid or unknown),
    }
