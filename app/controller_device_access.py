"""Bounded projection for controller device-access settings."""
from __future__ import annotations

from typing import Any

FIELDS = {
    "webControlHttp": "web_control_http",
    "webControlHttps": "web_control_https",
    "appDiscovery": "app_discovery",
}
MAX_SOURCE_FIELDS = 16


class ControllerDeviceAccessError(ValueError):
    """Raised when device-access settings do not match the documented shape."""


def project_controller_device_access(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerDeviceAccessError("response_invalid")

    settings: dict[str, bool] = {}
    invalid_count = 0
    for source, target in FIELDS.items():
        if source not in result:
            continue
        value = result[source]
        if isinstance(value, bool):
            settings[target] = value
        else:
            invalid_count += 1

    missing_count = sum(source not in result for source in FIELDS)
    unknown_count = len(set(result) - set(FIELDS))
    return {
        "data": {
            "settings": settings,
            "present_count": len(settings),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
