"""Redacted projection for the documented Multicast Listener Discovery GET."""
from __future__ import annotations

from typing import Any

MAX_FEATURE_DESCRIPTIONS = 64

class SiteMldSummaryError(ValueError):
    """Raised when the MLD setting cannot be projected safely."""

def summarize_site_mld(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        raise SiteMldSummaryError("response_invalid")
    allowed = {"enable", "version", "wanPortId", "featureDescription"}
    unknown = len(set(result) - allowed)
    missing = invalid = 0
    enabled_raw = result.get("enable")
    if type(enabled_raw) is bool:
        enabled: bool | None = enabled_raw
    else:
        enabled = None
        if "enable" not in result:
            missing += 1
        else:
            invalid += 1
    version_raw = result.get("version")
    if type(version_raw) is int and version_raw in (1, 2):
        version: int | None = version_raw
    else:
        version = None
        if "version" not in result:
            missing += 1
        else:
            invalid += 1
    port = result.get("wanPortId")
    if isinstance(port, str):
        port_configured: bool | None = bool(port.strip())
    else:
        port_configured = None
        if "wanPortId" not in result:
            missing += 1
        else:
            invalid += 1
    descriptions = result.get("featureDescription")
    if "featureDescription" not in result or descriptions is None:
        description_count: int | None = None
    elif isinstance(descriptions, list) and len(descriptions) <= MAX_FEATURE_DESCRIPTIONS and all(
            isinstance(item, dict) for item in descriptions):
        description_count = len(descriptions)
        for item in descriptions:
            unknown += len(set(item) - {"feature", "description", "support"})
    else:
        description_count = None
        invalid += 1
    return {"data": {"enabled": enabled, "version": version,
                     "wan_port_configured": port_configured,
                     "feature_description_count": description_count},
            "missing_field_count": missing, "invalid_field_count": invalid,
            "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
