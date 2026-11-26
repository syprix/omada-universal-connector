"""Redacted aggregates for the Hotspot rate-limit profile inventory."""
from __future__ import annotations

from collections.abc import Mapping


class SiteHotspotRateLimitProfilesError(ValueError):
    pass


_LIMIT_MIN = 1
_LIMIT_MAX = 10_485_760
_MAX_PROFILES = 1_000
_KNOWN_FIELDS = frozenset({
    "id", "name", "site", "downLimitEnable", "downLimit", "upLimitEnable",
    "upLimit", "isDefault", "resource",
})
_MISSING = object()


def summarize_hotspot_rate_limit_profiles(rows: object) -> dict[str, object]:
    if not isinstance(rows, list) or len(rows) > _MAX_PROFILES:
        raise SiteHotspotRateLimitProfilesError("inventory_invalid")

    directions: dict[str, dict[str, object]] = {
        name: {
            "enable_counts": {"enabled": 0, "disabled": 0, "missing": 0, "invalid": 0},
            "enabled_limit_coverage": {"reported": 0, "valid": 0, "missing": 0, "invalid": 0},
            "enabled_limit_kbps": {"count": 0, "sum": 0, "min": None, "max": None},
        }
        for name in ("downstream", "upstream")
    }
    default_counts = {"true": 0, "false": 0, "missing": 0, "invalid": 0}
    invalid_profiles = unknown_fields = 0
    partial = False

    field_pairs = (
        ("downstream", "downLimitEnable", "downLimit"),
        ("upstream", "upLimitEnable", "upLimit"),
    )
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 16:
            invalid_profiles += 1
            partial = True
            continue
        unknown_fields += sum(key not in _KNOWN_FIELDS for key in row)
        partial |= any(key not in _KNOWN_FIELDS for key in row)

        for direction, enabled_key, limit_key in field_pairs:
            aggregate = directions[direction]
            enable_counts = aggregate["enable_counts"]
            coverage = aggregate["enabled_limit_coverage"]
            kbps = aggregate["enabled_limit_kbps"]
            enabled = row.get(enabled_key, _MISSING)
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
                # A disabled-side numeric field has no documented active-limit meaning.
                continue

            enable_counts["enabled"] += 1
            value = row.get(limit_key, _MISSING)
            if value is _MISSING or value is None:
                coverage["missing"] += 1
                partial = True
                continue
            coverage["reported"] += 1
            if type(value) is not int or not _LIMIT_MIN <= value <= _LIMIT_MAX:
                coverage["invalid"] += 1
                partial = True
                continue
            coverage["valid"] += 1
            kbps["count"] += 1
            kbps["sum"] += value
            kbps["min"] = value if kbps["min"] is None else min(kbps["min"], value)
            kbps["max"] = value if kbps["max"] is None else max(kbps["max"], value)

        is_default = row.get("isDefault", _MISSING)
        if is_default is _MISSING:
            default_counts["missing"] += 1
            partial = True
        elif type(is_default) is not bool:
            default_counts["invalid"] += 1
            partial = True
        else:
            default_counts["true" if is_default else "false"] += 1

    return {
        "profile_count": len(rows),
        "directional_coverage": directions,
        "default_profile_counts": default_counts,
        "invalid_profile_count": invalid_profiles,
        "unknown_field_count": unknown_fields,
        "partial": bool(partial or invalid_profiles or unknown_fields),
        "disabled_limit_values_counted": False,
        "policy_application_to_clients_inferred": False,
        "profile_names_ids_sites_and_raw_values_returned": False,
    }
