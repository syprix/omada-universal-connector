"""Redacted projection for site-template inventory rows."""
from __future__ import annotations

from typing import Any

MAX_SETTINGS = 64


class SiteTemplateSummaryError(ValueError):
    """Raised when a site-template row cannot be summarized safely."""


def summarize_site_template(row: Any, *, template_ref: str,
                            expose_name: bool = False) -> dict[str, object]:
    if not isinstance(row, dict):
        raise SiteTemplateSummaryError("response_invalid")
    unknown = len(set(row) - {
        "id", "omadacId", "name", "status", "bindSiteNum", "category", "type", "settings",
    })
    invalid = 0
    data: dict[str, object] = {"site_template_ref": template_ref}
    type_value = row.get("type")
    if type(type_value) is int and type_value in (0, 1):
        data["template_type"] = "basic" if type_value == 0 else "pro"
    else:
        data["template_type"] = None
        if "type" in row:
            invalid += 1
    bound = row.get("bindSiteNum")
    if type(bound) is int and bound >= 0:
        data["bound_site_count"] = bound
    else:
        data["bound_site_count"] = None
        if "bindSiteNum" in row:
            invalid += 1
    settings = row.get("settings")
    if isinstance(settings, list) and len(settings) <= MAX_SETTINGS and all(
            isinstance(value, str) for value in settings):
        data["settings_count"] = len(settings)
    else:
        data["settings_count"] = None
        if "settings" in row:
            invalid += 1
    if expose_name:
        name = row.get("name")
        if isinstance(name, str) and name.strip() and len(name) <= 64:
            data["template_name"] = name.strip()
        elif "name" in row:
            invalid += 1
        category = row.get("category")
        if isinstance(category, str) and len(category) <= 64:
            data["template_category"] = category
        elif "category" in row and category is not None:
            invalid += 1
    return {"data": data, "invalid_field_count": invalid,
            "unknown_field_count": unknown, "partial": bool(invalid or unknown)}
