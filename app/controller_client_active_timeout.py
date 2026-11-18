"""Projection for the controller's client active-timeout setting."""
from __future__ import annotations

from typing import Any


class ControllerClientActiveTimeoutError(ValueError):
    """Raised when the response is not a bounded object."""


def project_controller_client_active_timeout(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 16:
        raise ControllerClientActiveTimeoutError("response_invalid")
    raw = result.get("clientActiveTimeoutMin")
    value = raw if type(raw) is int and -(2**31) <= raw <= 2**31 - 1 else None
    missing_count = int("clientActiveTimeoutMin" not in result)
    invalid_count = int("clientActiveTimeoutMin" in result and value is None)
    unknown_field_count = len(set(result) - {"clientActiveTimeoutMin"})
    return {
        "data": {
            "active_timeout_minutes": value,
            "present_count": int(value is not None),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_field_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_field_count),
    }
