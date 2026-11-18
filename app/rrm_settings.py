"""Strict redacted projection of the documented RRM GET response."""
from __future__ import annotations

from typing import Any


class RrmSettingsError(ValueError):
    """A response cannot be projected safely; carries only a stable code."""

    def __init__(self, code: str = "rrm_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 64
_INT32_MAX = 2_147_483_647
_EXPECTED = ("mode", "timeRangeEnable", "resource", "timeRangeAction")
_ENUMS = {
    "mode": frozenset({0, 1}),
    "resource": frozenset({0, 1, 2}),
    "timeRangeAction": frozenset({0, 1}),
}


def _valid_int(value: Any, allowed: frozenset[int]) -> bool:
    return type(value) is int and 0 <= value <= _INT32_MAX and value in allowed


def project_rrm_settings(raw: object) -> dict[str, object]:
    """Project an RRM ``result`` object without exposing profile IDs.

    Documented enum values are retained; unknown enum values, malformed or
    additional fields, absent values, and the sensitive ``timeRangeId`` are
    represented by ``partial`` and ``omitted_fields`` metadata.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise RrmSettingsError()

    data: dict[str, object] = {}
    omitted: set[str] = set()
    omitted_count = 0
    for field in _EXPECTED:
        if field not in raw:
            omitted.add(field)
            omitted_count += 1
            continue
        value = raw[field]
        if field == "timeRangeEnable":
            if type(value) is bool:
                data[field] = value
            else:
                omitted.add(field)
                omitted_count += 1
        elif _valid_int(value, _ENUMS[field]):
            data[field] = value
        else:
            omitted.add(field)
            omitted_count += 1

    for field in raw:
        if field not in _EXPECTED:
            # Includes timeRangeId and every unrecognized vendor extension.
            if field == "timeRangeId":
                omitted.add("timeRangeId")
            else:
                omitted.add("unknown_fields")
            omitted_count += 1

    ordered_omitted = sorted(omitted)
    return {
        "status": "ok",
        "resource": "rrm_settings",
        "data": data,
        "partial": bool(ordered_omitted),
        "omitted_field_count": omitted_count,
        "omitted_fields": ordered_omitted,
    }
