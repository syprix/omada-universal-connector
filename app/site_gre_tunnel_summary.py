"""Redacted projection for the documented site EoGRE tunnel settings GET."""
from __future__ import annotations

from typing import Any

_FIELDS = {"greEnable", "tunnelMtu", "interval", "maxCount", "primaryAddress", "secondaryAddress"}
_RANGES = {"tunnelMtu": (850, 1500), "interval": (10, 600), "maxCount": (3, 10)}

class SiteGreTunnelSummaryError(ValueError):
    """Raised when a GRE tunnel response cannot be projected safely."""

def summarize_site_gre_tunnel(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        raise SiteGreTunnelSummaryError("response_invalid")
    missing = invalid = 0
    unknown = len(set(result) - _FIELDS)
    enabled_raw = result.get("greEnable")
    if type(enabled_raw) is bool:
        enabled: bool | None = enabled_raw
    else:
        enabled = None
        if "greEnable" not in result:
            missing += 1
        else:
            invalid += 1
    numeric: dict[str, int | None] = {}
    for field, (low, high) in _RANGES.items():
        value = result.get(field)
        if type(value) is int and low <= value <= high:
            numeric[field] = value
        else:
            numeric[field] = None
            if field not in result:
                missing += 1
            else:
                invalid += 1
    address_flags: dict[str, bool | None] = {}
    for field, output in (("primaryAddress", "primary_endpoint_configured"),
                          ("secondaryAddress", "secondary_endpoint_configured")):
        value = result.get(field)
        if isinstance(value, str):
            address_flags[output] = bool(value.strip())
        else:
            address_flags[output] = None
            if field not in result:
                missing += 1
            else:
                invalid += 1
    data = {"enabled": enabled, "tunnel_mtu": numeric["tunnelMtu"],
            "keepalive_interval_seconds": numeric["interval"],
            "keepalive_miss_limit": numeric["maxCount"], **address_flags}
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
