"""Redacted projection for the documented controller critical-model count."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_INT32_MAX = (1 << 31) - 1


class ControllerFirmwareCriticalModelCountError(ValueError):
    """The documented response container is not an object."""


def project_critical_model_count(result: Any) -> dict[str, object]:
    """Expose only a valid nonnegative critical-model count and coverage flags."""
    if result is None:
        result = {}
    if not isinstance(result, Mapping):
        raise ControllerFirmwareCriticalModelCountError

    present = "criticalNumber" in result
    value = result.get("criticalNumber")
    valid = present and type(value) is int and 0 <= value <= _INT32_MAX
    unknown_count = sum(1 for key in result if key != "criticalNumber")
    missing_count = int(not present)
    invalid_count = int(present and not valid)
    return {
        "critical_model_count": value if valid else None,
        "count_present": present,
        "missing_field_count": missing_count,
        "invalid_field_count": invalid_count,
        "unknown_field_count": unknown_count,
        "coverage_complete": bool(valid and unknown_count == 0),
        "partial": bool(not valid or unknown_count),
    }
