"""Projection for the documented site WAN maximum-speed configuration."""

from __future__ import annotations

from collections.abc import Mapping


class SiteWanMaxSpeedError(ValueError):
    """The controller response has an invalid outer shape."""


_INT32_MIN = -(2 ** 31)
_INT32_MAX = 2 ** 31 - 1
_FIELDS = ("upstream", "downstream")


def project_site_wan_max_speed(result: object) -> dict[str, object]:
    """Return the two documented int32 values without assuming a unit."""
    if not isinstance(result, Mapping) or len(result) > 16:
        raise SiteWanMaxSpeedError("result must be a bounded object")
    missing = invalid = 0
    values: dict[str, int | None] = {}
    for field in _FIELDS:
        value = result.get(field)
        if field not in result:
            missing += 1
            values[field] = None
        elif (isinstance(value, bool) or not isinstance(value, int) or
              value < _INT32_MIN or value > _INT32_MAX):
            invalid += 1
            values[field] = None
        else:
            values[field] = value
    unknown = sum(key not in _FIELDS for key in result)
    return {
        "data": {**values, "unit": "unspecified_by_source"},
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
