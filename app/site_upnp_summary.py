"""Redacted projection for the documented site UPnP settings GET."""
from __future__ import annotations

from typing import Any

MAX_REFERENCES = 256

class SiteUpnpSummaryError(ValueError):
    """Raised when a UPnP setting cannot be projected safely."""

def summarize_site_upnp(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        raise SiteUpnpSummaryError("response_invalid")
    missing = invalid = unknown = 0
    allowed = {"enable", "wanPortIds", "networkIds", "supportByDsLiteAndMapE"}
    unknown += len(set(result) - allowed)
    def boolean(name: str) -> bool | None:
        nonlocal missing, invalid
        value = result.get(name)
        if type(value) is bool:
            return value
        if name not in result:
            missing += 1
        else:
            invalid += 1
        return None
    enabled = boolean("enable")
    supports_dslite = boolean("supportByDsLiteAndMapE")
    counts: dict[str, int | None] = {}
    for field, output in (("wanPortIds", "wan_port_count"), ("networkIds", "network_count")):
        values = result.get(field)
        if isinstance(values, list) and len(values) <= MAX_REFERENCES and all(
                isinstance(value, str) and value for value in values):
            counts[output] = len(values)
        else:
            counts[output] = None
            if field not in result:
                missing += 1
            else:
                invalid += 1
    return {"data": {"enabled": enabled, **counts,
                    "supports_ds_lite_or_map_e": supports_dslite},
            "missing_field_count": missing, "invalid_field_count": invalid,
            "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
