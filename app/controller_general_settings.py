"""Bounded projection for global controller identity, locale and DST settings."""
from __future__ import annotations

import string
from typing import Any

try:
    from .controller_dst_info import ControllerDstError, project_controller_dst
except ImportError:  # direct execution in the image
    from controller_dst_info import ControllerDstError, project_controller_dst

KNOWN_FIELDS = {"name", "timeZone", "region", "dst"}
MAX_SOURCE_FIELDS = 8
MAX_NAME_LENGTH = 32
MAX_LOCALE_LENGTH = 128


class ControllerGeneralSettingsError(ValueError):
    """Raised when general settings exceed their documented bounds."""


def project_controller_general_settings(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerGeneralSettingsError("response_invalid")
    settings: dict[str, str] = {}
    invalid_count = 0
    for source, target, maximum in (
        ("name", "name", MAX_NAME_LENGTH),
        ("timeZone", "time_zone", MAX_LOCALE_LENGTH),
        ("region", "region", MAX_LOCALE_LENGTH),
    ):
        if source not in result:
            continue
        value = result[source]
        valid = isinstance(value, str) and 0 < len(value) <= maximum
        if source == "name" and valid:
            valid = all(char in string.printable and char not in "\r\n\t\x0b\x0c" for char in value)
        if valid:
            settings[target] = value
        else:
            invalid_count += 1
    dst: dict[str, object] | None = None
    if "dst" in result:
        try:
            dst = project_controller_dst(result["dst"])
        except ControllerDstError:
            invalid_count += 1
    missing_count = sum(source not in result for source in {"name", "timeZone", "region"})
    unknown_count = len(set(result) - KNOWN_FIELDS)
    dst_partial = bool(dst and dst.get("partial"))
    dst_data = dst.get("data", {}) if dst else {}
    dst_present = dst_data.get("present_count", 0) if isinstance(dst_data, dict) else 0
    return {
        "data": {
            "settings": settings,
            "dst": dst_data if dst is not None else None,
            "present_count": len(settings) + dst_present,
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count or dst_partial),
    }
