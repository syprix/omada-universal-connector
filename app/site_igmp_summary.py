"""Redacted projection for the documented site IGMP settings GET."""
from __future__ import annotations

from typing import Any

MAX_FEATURE_DESCRIPTIONS = 64
_FIELDS = {"enable", "version", "wanPortId", "virtualWanId", "featureDescription"}
_FEATURE_FIELDS = {"feature", "description", "support"}


class SiteIgmpSummaryError(ValueError):
    """Raised when the IGMP setting cannot be projected safely."""


def summarize_site_igmp(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        raise SiteIgmpSummaryError("response_invalid")
    unknown = len(set(result) - _FIELDS)
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
    if type(version_raw) is int and version_raw in (2, 3):
        version: int | None = version_raw
    else:
        version = None
        if "version" not in result:
            missing += 1
        else:
            invalid += 1
    wan = result.get("wanPortId")
    if isinstance(wan, str):
        wan_configured: bool | None = bool(wan.strip())
    else:
        wan_configured = None
        if "wanPortId" in result:
            invalid += 1
    virtual_wan = result.get("virtualWanId")
    if isinstance(virtual_wan, str):
        virtual_wan_configured: bool | None = bool(virtual_wan.strip())
    else:
        virtual_wan_configured = None
        if "virtualWanId" in result:
            invalid += 1
    descriptions = result.get("featureDescription")
    if descriptions is None:
        description_count: int | None = None
    elif isinstance(descriptions, list) and len(descriptions) <= MAX_FEATURE_DESCRIPTIONS and all(
            isinstance(item, dict) for item in descriptions):
        description_count = len(descriptions)
        for item in descriptions:
            unknown += len(set(item) - _FEATURE_FIELDS)
    else:
        description_count = None
        invalid += 1
    return {
        "data": {
            "enabled": enabled,
            "version": version,
            "wan_port_configured": wan_configured,
            "virtual_wan_configured": virtual_wan_configured,
            "feature_description_count": description_count,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }


def summarize_site_template_igmp(result: Any) -> dict[str, object]:
    """Project the CBC site-template IGMP schema, which requires a WAN ID."""
    if not isinstance(result, dict):
        raise SiteIgmpSummaryError("response_invalid")
    allowed = {"enable", "version", "wanPortId"}
    unknown = len(set(result) - allowed)
    missing = invalid = 0
    enabled_raw = result.get("enable")
    if type(enabled_raw) is bool:
        enabled: bool | None = enabled_raw
    else:
        enabled = None
        if "enable" not in result: missing += 1
        else: invalid += 1
    version_raw = result.get("version")
    if type(version_raw) is int and version_raw in (2, 3):
        version: int | None = version_raw
    else:
        version = None
        if "version" not in result: missing += 1
        else: invalid += 1
    wan = result.get("wanPortId")
    if isinstance(wan, str):
        wan_configured: bool | None = bool(wan.strip())
    else:
        wan_configured = None
        if "wanPortId" not in result: missing += 1
        else: invalid += 1
    return {
        "data": {"enabled": enabled, "version": version,
                 "wan_port_configured": wan_configured},
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
