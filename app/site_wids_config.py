"""Bounded projection for the read-only site wireless IDS configuration."""

from __future__ import annotations

from collections.abc import Mapping


class SiteWidsConfigError(ValueError):
    """The controller response is too large or has an invalid outer shape."""


def _int32(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and -(2**31) <= value < 2**31


def project_site_wids_config(result: object) -> dict[str, object]:
    """Project only fields common to the three source exports.

    Detection codes are retained as int32 values because the exports disagree
    about whether code 15 is part of their documented enum.
    """
    if not isinstance(result, Mapping) or len(result) > 16:
        raise SiteWidsConfigError("result must be a bounded object")

    missing = invalid = 0
    unknown = sum(key not in {"status", "level", "detection"} for key in result)

    status = result.get("status")
    if "status" not in result:
        missing += 1
        status = None
    elif not isinstance(status, bool):
        invalid += 1
        status = None

    level = result.get("level")
    if "level" not in result:
        missing += 1
        level = None
    elif not _int32(level) or level not in (0, 1, 2):
        invalid += 1
        level = None

    detection_codes: list[int] | None = None
    if "detection" in result:
        raw_codes = result.get("detection")
        if (not isinstance(raw_codes, list) or len(raw_codes) > 32 or
                any(not _int32(code) for code in raw_codes)):
            invalid += 1
        else:
            detection_codes = list(raw_codes)
    elif level == 2:
        missing += 1

    return {
        "data": {
            "enabled": status,
            "detection_level_code": level,
            "detection_codes_applicable": level == 2 if level is not None else None,
            "detection_codes": detection_codes,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid),
    }
