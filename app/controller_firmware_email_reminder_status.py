"""Projection for the controller's firmware email-reminder switch."""
from __future__ import annotations

from typing import Any


class ControllerFirmwareEmailReminderStatusError(ValueError):
    """Raised when the documented result is not a bounded object."""


def project_firmware_email_reminder_status(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise ControllerFirmwareEmailReminderStatusError("response_invalid")
    enabled: bool | None = None
    invalid_count = 0
    if "enable" in result:
        value = result["enable"]
        if type(value) is bool:
            enabled = value
        else:
            invalid_count += 1
    missing_count = int("enable" not in result)
    unknown_count = len(set(result) - {"enable"})
    return {
        "data": {
            "firmware_email_reminder_enabled": enabled,
            "present_count": int(enabled is not None),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
