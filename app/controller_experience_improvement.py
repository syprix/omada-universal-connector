"""Projection for the controller experience-improvement participation flag."""
from __future__ import annotations

from typing import Any


class ControllerExperienceImprovementError(ValueError):
    """Raised when the documented result is not a bounded object."""


def project_controller_experience_improvement(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise ControllerExperienceImprovementError("response_invalid")
    enabled: bool | None = None
    invalid_count = 0
    if "expImprove" in result:
        value = result["expImprove"]
        if type(value) is bool:
            enabled = value
        else:
            invalid_count += 1
    missing_count = int("expImprove" not in result)
    unknown_count = len(set(result) - {"expImprove"})
    return {
        "data": {
            "experience_improvement_enabled": enabled,
            "present_count": int(enabled is not None),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
