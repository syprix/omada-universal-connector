"""Strict projection for a device's online-upgrade task result."""
from __future__ import annotations

from typing import Any

FIELDS = {"finished", "success"}


class DeviceUpgradeResultError(ValueError):
    """Raised when the upgrade-result response has an invalid shape."""


def project_device_upgrade_result(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > len(FIELDS):
        raise DeviceUpgradeResultError("response_invalid")
    projected: dict[str, bool | None] = {"finished": None, "success": None}
    invalid = 0
    for field in FIELDS:
        if field not in result:
            continue
        value = result[field]
        if type(value) is bool:
            projected[field] = value
        else:
            invalid += 1
    missing = len(FIELDS - result.keys())
    unknown = len(result.keys() - FIELDS)
    return {
        "data": {"finished": projected["finished"], "success": projected["success"],
                 "present_count": sum(value is not None for value in projected.values()),
                 "missing_count": missing, "invalid_count": invalid,
                 "unknown_field_count": unknown},
        "partial": bool(missing or invalid or unknown),
    }
