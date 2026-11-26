"""Redacted aggregates for the site-wide rate-limit profile inventory."""
from __future__ import annotations

from collections.abc import Mapping


_MAX_PROFILES = 1_000
_MAX_PROFILE_FIELDS = 32
_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1
_KNOWN_FIELDS = frozenset({
    "profileId", "name", "downLimitEnable", "downLimit", "upLimitEnable",
    "upLimit", "defaultProfile", "resource",
})
_MISSING = object()


class SiteRateLimitProfilesError(ValueError):
    """Raised when the fixed site profile response is malformed or over bound."""


def _empty_direction() -> dict[str, object]:
    return {
        "enable_counts": {"enabled": 0, "disabled": 0, "missing": 0, "invalid": 0},
        "enabled_limit_coverage": {"reported": 0, "valid": 0, "missing": 0, "invalid": 0},
        "enabled_limit_kbps": {"count": 0, "sum": 0, "min": None, "max": None},
    }


def summarize_site_rate_limit_profiles(rows: object) -> dict[str, object]:
    if not isinstance(rows, list) or len(rows) > _MAX_PROFILES:
        raise SiteRateLimitProfilesError("response_invalid")

    directions = {"downstream": _empty_direction(), "upstream": _empty_direction()}
    default_counts = {"true": 0, "false": 0, "missing": 0, "invalid": 0}
    invalid_profiles = unknown_fields = 0
    partial = False

    for row in rows:
        if not isinstance(row, Mapping) or len(row) > _MAX_PROFILE_FIELDS:
            invalid_profiles += 1
            partial = True
            continue
        unknown = sum(key not in _KNOWN_FIELDS for key in row)
        unknown_fields += unknown
        partial |= bool(unknown)

        for direction, enable_key, limit_key in (
            ("downstream", "downLimitEnable", "downLimit"),
            ("upstream", "upLimitEnable", "upLimit"),
        ):
            aggregate = directions[direction]
            enable_counts = aggregate["enable_counts"]
            coverage = aggregate["enabled_limit_coverage"]
            kbps = aggregate["enabled_limit_kbps"]
            enabled = row.get(enable_key, _MISSING)
            if enabled is _MISSING:
                enable_counts["missing"] += 1
                partial = True
                continue
            if type(enabled) is not bool:
                enable_counts["invalid"] += 1
                partial = True
                continue
            if not enabled:
                enable_counts["disabled"] += 1
                continue

            enable_counts["enabled"] += 1
            value = row.get(limit_key, _MISSING)
            if value is _MISSING:
                coverage["missing"] += 1
                partial = True
                continue
            coverage["reported"] += 1
            if (type(value) is not int or not _INT64_MIN <= value <= _INT64_MAX):
                coverage["invalid"] += 1
                partial = True
                continue
            coverage["valid"] += 1
            kbps["count"] += 1
            kbps["sum"] += value
            kbps["min"] = value if kbps["min"] is None else min(kbps["min"], value)
            kbps["max"] = value if kbps["max"] is None else max(kbps["max"], value)

        default = row.get("defaultProfile", _MISSING)
        if default is _MISSING:
            default_counts["missing"] += 1
            partial = True
        elif type(default) is not bool:
            default_counts["invalid"] += 1
            partial = True
        else:
            default_counts["true" if default else "false"] += 1

    return {
        "profile_count": len(rows),
        "empty": not rows,
        "directional_coverage": directions,
        "default_profile_counts": default_counts,
        "invalid_profile_count": invalid_profiles,
        "unknown_field_count": unknown_fields,
        "server_completeness": "not_reported_by_contract",
        "partial": bool(partial or invalid_profiles or unknown_fields),
    }
