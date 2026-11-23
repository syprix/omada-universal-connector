"""Redacted site URL-filter global settings."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def summarize_url_filter_general(payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("input_invalid")
    settings = {}
    partial = False
    for field in ("safeSearch", "blockPage"):
        value = payload.get(field)
        if type(value) is bool:
            settings[field] = "enabled" if value else "disabled"
        else:
            settings[field] = "unknown"
            partial = True
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_url_filter_general_summary",
        "reported_settings": settings,
        "block_page_message_returned": False,
        "enforcement_inferred": False,
        "partial": partial,
    }
