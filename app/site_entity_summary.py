"""Redacted projection for the documented site-entity GET response."""
from __future__ import annotations

import math
from typing import Any


class SiteEntitySummaryError(ValueError):
    """Raised when the source does not return a site entity object."""


_SITE_FIELDS = frozenset({
    "siteId", "name", "type", "tagIds", "region", "timeZone", "ntpEnable",
    "ntpServers", "dst", "scenario", "longitude", "latitude", "address",
    "supportES", "supportL2",
})
_DST_FIELDS = frozenset({
    "enable", "mode", "start", "end", "status", "startTime", "endTime",
    "offset", "nextStart", "nextEnd", "timeZone", "lastStart", "lastEnd",
})


def summarize_site_entity(value: Any) -> dict[str, object]:
    """Keep only site tier and time/feature status; discard all site identity/location data."""
    if not isinstance(value, dict):
        raise SiteEntitySummaryError("site_entity_invalid")

    missing = 0
    invalid = 0
    unknown = sum(1 for key in value if key not in _SITE_FIELDS)

    raw_type = value.get("type")
    if type(raw_type) is int and raw_type in (0, 1):
        tier: str | None = "basic" if raw_type == 0 else "pro"
    else:
        tier = None
        if "type" not in value:
            missing += 1
        else:
            invalid += 1

    def boolean_field(name: str) -> bool | None:
        nonlocal missing, invalid
        raw = value.get(name)
        if type(raw) is bool:
            return raw
        if name not in value:
            missing += 1
        else:
            invalid += 1
        return None

    ntp_enabled = boolean_field("ntpEnable")
    supports_es = boolean_field("supportES")
    supports_l2 = boolean_field("supportL2")

    timezone = value.get("timeZone")
    if isinstance(timezone, str):
        timezone_configured: bool | None = bool(timezone.strip())
    else:
        timezone_configured = None
        if "timeZone" not in value:
            missing += 1
        else:
            invalid += 1

    servers = value.get("ntpServers")
    if isinstance(servers, list) and len(servers) <= 5 and all(
            isinstance(item, str) for item in servers):
        ntp_server_count: int | None = len(servers)
    else:
        ntp_server_count = None
        if "ntpServers" not in value:
            missing += 1
        else:
            invalid += 1

    dst = value.get("dst")
    if isinstance(dst, dict):
        unknown += sum(1 for key in dst if key not in _DST_FIELDS)
        raw_dst = dst.get("enable")
        if type(raw_dst) is bool:
            dst_enabled: bool | None = raw_dst
        else:
            dst_enabled = None
            if "enable" not in dst:
                missing += 1
            else:
                invalid += 1
    else:
        dst_enabled = None
        if "dst" not in value:
            missing += 1
        else:
            invalid += 1

    # Coordinates are only validated to produce a presence flag; values never leave this function.
    coordinate_values: list[float] = []
    for key, low, high in (("longitude", -180, 180), ("latitude", -90, 90)):
        raw = value.get(key)
        try:
            numeric = float(raw) if isinstance(raw, (int, float)) and type(raw) is not bool else None
            valid = numeric is not None and math.isfinite(numeric) and low <= numeric <= high
        except (OverflowError, ValueError):
            valid = False
            numeric = None
        if valid and numeric is not None:
            coordinate_values.append(numeric)
        elif key in value:
            invalid += 1
    location_configured = len(coordinate_values) == 2 if len(coordinate_values) == 2 else None
    if location_configured is None and ("longitude" not in value or "latitude" not in value):
        missing += int("longitude" not in value) + int("latitude" not in value)

    return {
        "data": {
            "site_tier": tier,
            "ntp_enabled": ntp_enabled,
            "ntp_server_count": ntp_server_count,
            "timezone_configured": timezone_configured,
            "dst_enabled": dst_enabled,
            "location_configured": location_configured,
            "supports_agile_switches": supports_es,
            "supports_non_agile_switches": supports_l2,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
