"""Validated projection for controller log-level settings."""
from __future__ import annotations

from typing import Any

FIELDS = {
    "type": {"AUTO", "CUSTOM"},
    "otherModule": {"WARN", "INFO", "DEBUG"},
    "managerModule": {"WARN", "INFO", "DEBUG"},
    "clientModule": {"WARN", "INFO", "DEBUG"},
    "monitorModule": {"WARN", "INFO", "DEBUG"},
    "systemModule": {"WARN", "INFO", "DEBUG"},
    "accountModule": {"WARN", "INFO", "DEBUG"},
    "logModule": {"WARN", "INFO", "DEBUG"},
}
MAX_SOURCE_FIELDS = len(FIELDS)


class ControllerLoggingError(ValueError):
    """Raised when the logging settings response is not a bounded object."""


def project_controller_logging(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerLoggingError("response_invalid")
    levels: dict[str, str] = {}
    invalid = 0
    for field, allowed in FIELDS.items():
        if field not in result:
            continue
        value = result[field]
        if isinstance(value, str) and value in allowed:
            levels[field] = value
        else:
            invalid += 1
    missing = len(FIELDS.keys() - result.keys())
    unknown = len(result.keys() - FIELDS.keys())
    return {
        "data": {"levels": levels, "present_count": len(levels),
                 "missing_count": missing, "invalid_count": invalid,
                 "unknown_field_count": unknown},
        "partial": bool(missing or invalid or unknown),
    }
