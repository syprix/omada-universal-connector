"""Redacted IDS/IPS configuration projection for a selected Omada site."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def summarize_site_ids_ips_config(result: object) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("invalid IDS/IPS configuration")

    unknown: list[str] = []
    missing: list[str] = []

    def boolean(name: str) -> bool | None:
        if name not in result:
            missing.append(name)
            return None
        value = result.get(name)
        if type(value) is not bool:
            unknown.append(name)
            return None
        return value

    def code(name: str, allowed: set[int]) -> int | None:
        if name not in result:
            missing.append(name)
            return None
        value = result.get(name)
        if type(value) is not int or value not in allowed:
            unknown.append(name)
            return None
        return value

    enabled = boolean("enable")
    mode = code("ipsMode", {0, 1})
    level = code("dpLevel", {0, 1, 2, 3})
    geo_enabled = boolean("geoEnable")
    category_field = "customCategories"
    if category_field not in result:
        missing.append(category_field)
        category_count = None
    else:
        categories = result.get(category_field)
        documented_category_ids = {1, 2, 3, 4, 6, 7, 8, 9, 14, 15, 18, 24}
        if (not isinstance(categories, list) or len(categories) > 4096 or
                any(type(category) is not int or category not in documented_category_ids
                    for category in categories)):
            unknown.append(category_field)
            category_count = None
        else:
            category_count = len(categories)

    return {
        "enable": enabled,
        "ips_mode": mode,
        "dp_level": level,
        "geo_enable": geo_enabled,
        "custom_category_count": category_count,
        "unknown_fields": unknown,
        "missing_fields": missing,
        "configuration_only": True,
    }
