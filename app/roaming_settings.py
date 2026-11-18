"""Strict, redacted projection of site roaming settings."""
from __future__ import annotations

from typing import Any


class RoamingSettingsError(ValueError):
    """The response cannot be safely projected; exposes no raw values."""

    def __init__(self, code: str = "roaming_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_TOP_LEVEL_FIELDS = 32
_MAX_ROAMING_FIELDS = 32
_FIELDS = (
    "fastRoamingEnable",
    "aiRoamingEnable",
    "dualBand11kReportEnable",
    "forceDisassociationEnable",
    "nonStickRoamingEnable",
)


def project_roaming_settings(raw: object) -> dict[str, object]:
    """Project documented ``result.roaming`` booleans only.

    Missing, malformed, and unknown fields are not inferred. Metadata names
    only the fixed schema fields or an aggregate unknown-field label.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_TOP_LEVEL_FIELDS:
        raise RoamingSettingsError()

    data: dict[str, bool] = {}
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0

    roaming = raw.get("roaming")
    if not isinstance(roaming, dict):
        if "roaming" not in raw:
            missing.append("roaming")
        else:
            omitted.add("roaming")
            omitted_count += 1
    else:
        if len(roaming) > _MAX_ROAMING_FIELDS:
            raise RoamingSettingsError()
        for field in _FIELDS:
            if field not in roaming:
                missing.append(field)
            elif type(roaming[field]) is bool:
                data[field] = roaming[field]
            else:
                omitted.add(field)
                omitted_count += 1
        unknown_count = sum(1 for field in roaming if field not in _FIELDS)
        if unknown_count:
            omitted.add("unknown_fields")
            omitted_count += unknown_count

    unknown_top_level = sum(1 for field in raw if field != "roaming")
    if unknown_top_level:
        omitted.add("unknown_fields")
        omitted_count += unknown_top_level
    omitted_count += len(missing)

    return {
        "status": "ok",
        "resource": "roaming_settings",
        "data": data,
        "partial": bool(missing or omitted_count),
        "missing_fields": missing,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
    }
