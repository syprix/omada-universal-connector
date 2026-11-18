"""Bounded projection for the site remember-device setting."""
from __future__ import annotations

from typing import Any


class SiteRememberSettingError(ValueError):
    """Raised when the remember-device response is outside its small schema."""


def project_site_remember_setting(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise SiteRememberSettingError("response_invalid")
    missing = int("remember" not in result)
    invalid = 0
    unknown = len(set(result) - {"remember"})
    data: dict[str, object] = {}
    if "remember" in result:
        if type(result["remember"]) is bool:
            data["remember_enabled"] = result["remember"]
        else:
            invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
