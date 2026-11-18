"""Redacted projection for controller UI preferences and private-label flags."""
from __future__ import annotations

from typing import Any

INT_FIELDS = {
    "timeZone": ("time_zone_code", 0, 3),
    "refreshRate": ("refresh_rate_code", 0, 4),
    "macFormat": ("mac_format_code", None, None),
}
BOOL_FIELD = "privateLabelingEnable"
REDACTED_STRING_FIELDS = {
    "privateLabelingUrl", "privateLabelingFileId", "privateLabelingFileName",
}
KNOWN_FIELDS = set(INT_FIELDS) | {BOOL_FIELD} | REDACTED_STRING_FIELDS
MAX_SOURCE_FIELDS = 16
MAX_TEXT_LENGTH = 2048


class ControllerUiInterfaceError(ValueError):
    """Raised when the controller response is not a bounded object."""


def project_controller_ui_interface(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerUiInterfaceError("response_invalid")
    settings: dict[str, object] = {}
    invalid_count = 0
    redacted_presence: dict[str, bool] = {}
    redacted_count = 0
    for source, (target, minimum, maximum) in INT_FIELDS.items():
        if source not in result:
            continue
        value = result[source]
        valid = (type(value) is int and -(2**31) <= value <= 2**31 - 1)
        if valid and minimum is not None:
            valid = minimum <= value <= maximum
        if valid:
            settings[target] = value
        else:
            invalid_count += 1
    if BOOL_FIELD in result:
        value = result[BOOL_FIELD]
        if type(value) is bool:
            settings["private_labeling_enabled"] = value
        else:
            invalid_count += 1
    for source in REDACTED_STRING_FIELDS:
        if source not in result:
            continue
        value = result[source]
        valid = isinstance(value, str) and len(value) <= MAX_TEXT_LENGTH
        target = {
            "privateLabelingUrl": "private_label_url_present",
            "privateLabelingFileId": "private_label_file_id_present",
            "privateLabelingFileName": "private_label_file_name_present",
        }[source]
        redacted_presence[target] = valid and bool(value)
        if valid:
            redacted_count += 1
        else:
            invalid_count += 1
    missing_count = len(KNOWN_FIELDS) - sum(field in result for field in KNOWN_FIELDS)
    unknown_count = len(set(result) - KNOWN_FIELDS)
    return {
        "data": {
            "settings": settings,
            "redacted_presence": redacted_presence,
            "present_count": len(settings),
            "redacted_field_count": redacted_count,
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
