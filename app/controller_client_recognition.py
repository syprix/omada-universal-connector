"""Projection for the controller-wide client-recognition setting."""
from __future__ import annotations

from typing import Any


class ControllerClientRecognitionError(ValueError):
    """Raised when the response is not a bounded object."""


def project_controller_client_recognition(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 16:
        raise ControllerClientRecognitionError("response_invalid")
    value = result.get("enable")
    enabled = value if type(value) is bool else None
    missing_count = 0 if "enable" in result else 1
    invalid_count = int("enable" in result and enabled is None)
    unknown_field_count = len(set(result) - {"enable"})
    return {
        "data": {
            "enabled": enabled,
            "present_count": int(enabled is not None),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_field_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_field_count),
    }
