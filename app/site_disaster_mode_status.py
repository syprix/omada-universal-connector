"""Validated projection for the documented site disaster-mode status code."""
from __future__ import annotations

from typing import Any


class SiteDisasterModeStatusError(ValueError):
    """Raised when the disaster-mode response is not safely projectable."""


def project_site_disaster_mode_status(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteDisasterModeStatusError("disaster_mode_status_invalid")
    value = result.get("status")
    valid = type(value) is int and -(2**31) <= value <= 2**31 - 1
    unknown = len(set(result) - {"status"})
    return {
        "data": {"status_code": value if valid else None},
        "missing_field_count": int("status" not in result),
        "invalid_field_count": int("status" in result and not valid),
        "unknown_field_count": unknown,
        "partial": bool("status" not in result or not valid or unknown),
    }
