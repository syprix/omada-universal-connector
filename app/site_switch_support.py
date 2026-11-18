"""Bounded projection for documented site switch-family support flags."""
from __future__ import annotations

from typing import Any


FIELDS = {
    "supportES": "support_es",
    "supportL2": "support_l2",
}
MAX_SOURCE_FIELDS = 16


class SiteSwitchSupportError(ValueError):
    """Raised when a switch-support response exceeds its bounded projection."""


def project_site_switch_support(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise SiteSwitchSupportError("response_invalid")
    support: dict[str, bool] = {}
    invalid_count = 0
    for source, target in FIELDS.items():
        if source not in result:
            continue
        value = result[source]
        if type(value) is bool:
            support[target] = value
        else:
            invalid_count += 1
    missing_count = len(FIELDS) - sum(name in result for name in FIELDS)
    unknown_count = len(set(result) - set(FIELDS))
    return {
        "data": {
            "switch_support": support,
            "present_count": len(support),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
