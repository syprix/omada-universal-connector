"""Minimal projection for the site's RadSec device-compatibility check."""
from __future__ import annotations

from typing import Any


class DeviceRadsecSupportError(ValueError):
    """Raised when the controller response has an invalid shape."""


def project_device_radsec_support(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 1:
        raise DeviceRadsecSupportError("response_invalid")
    exist: bool | None = None
    invalid = 0
    if "exist" in result:
        if type(result["exist"]) is bool:
            exist = result["exist"]
        else:
            invalid = 1
    missing = int("exist" not in result)
    unknown = len(result.keys() - {"exist"})
    return {
        "data": {"unsupported_devices_exist": exist,
                 "present_count": int(exist is not None),
                 "missing_count": missing, "invalid_count": invalid,
                 "unknown_field_count": unknown},
        "partial": bool(missing or invalid or unknown),
    }
