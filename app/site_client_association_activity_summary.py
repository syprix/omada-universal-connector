"""Redacted client connection counts over a recent site dashboard interval."""
from __future__ import annotations

from typing import Any


class SiteClientAssociationActivitySummaryError(ValueError):
    """Raised when the association activity response is malformed."""


_FIELDS = {
    "total": ("total_clients", (1 << 31) - 1),
    "wiredClient": ("wired_clients", (1 << 31) - 1),
    "wirelessClient": ("wireless_clients", (1 << 31) - 1),
}


def project_site_client_association_activity_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteClientAssociationActivitySummaryError("response_invalid")
    data: dict[str, object] = {}
    missing = invalid = 0
    unknown = len(set(result) - set(_FIELDS))
    for field, (output, upper) in _FIELDS.items():
        if field not in result:
            missing += 1
            continue
        value = result[field]
        if type(value) is not int or not 0 <= value <= upper:
            invalid += 1
            continue
        data[output] = value
    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
