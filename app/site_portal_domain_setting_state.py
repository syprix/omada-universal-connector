"""Redacted state for the site portal domain auto-refresh setting."""
from __future__ import annotations

from typing import Any

MAX_URL_FIELD_LENGTH = 2_048
MAX_ROOT_FIELDS = 8


class SitePortalDomainSettingStateError(ValueError):
    """Raised when the site portal-domain response is not a bounded object."""


def project_site_portal_domain_setting_state(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_ROOT_FIELDS:
        raise SitePortalDomainSettingStateError("response_invalid")
    unknown_field_count = len(set(result) - {"autoRefresh", "url"})
    missing_field_count = 0
    invalid_field_count = 0
    auto_refresh_state = "present"
    auto_refresh_enabled: bool | None = None
    url_applicable: bool | None = None
    url_state = "not_evaluated"
    url_configured: bool | None = None

    if "autoRefresh" not in result:
        auto_refresh_state = "missing"
        missing_field_count += 1
    elif type(result["autoRefresh"]) is not bool:
        auto_refresh_state = "invalid"
        invalid_field_count += 1
    else:
        auto_refresh_enabled = result["autoRefresh"]
        url_applicable = not auto_refresh_enabled
        if auto_refresh_enabled:
            url_state = "not_applicable"
        elif "url" not in result:
            url_state = "missing"
            missing_field_count += 1
        else:
            value = result["url"]
            if (not isinstance(value, str) or len(value) > MAX_URL_FIELD_LENGTH or
                    any(not character.isprintable() for character in value)):
                url_state = "invalid"
                invalid_field_count += 1
            else:
                url_state = "present"
                url_configured = bool(value)

    data = {
        "auto_refresh_enabled": auto_refresh_enabled,
        "auto_refresh_state": auto_refresh_state,
        "url_applicable": url_applicable,
        "url_state": url_state,
        "url_configured": url_configured,
        "missing_field_count": missing_field_count,
        "invalid_field_count": invalid_field_count,
        "unknown_field_count": unknown_field_count,
    }
    return {"data": data,
            "partial": bool(missing_field_count or invalid_field_count or
                            unknown_field_count)}
