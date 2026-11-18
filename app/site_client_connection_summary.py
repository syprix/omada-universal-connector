"""Bounded aggregate of wired and wireless client counts for a site."""
from __future__ import annotations

from typing import Any


class SiteClientConnectionSummaryError(ValueError):
    """Raised when the client count response exceeds its small schema."""


_FIELDS = {"total", "wiredClient", "wirelessClient"}
_OUTPUTS = {"total": "total_client_count",
            "wiredClient": "wired_client_count",
            "wirelessClient": "wireless_client_count"}


def project_site_client_connection_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 6:
        raise SiteClientConnectionSummaryError("response_invalid")
    missing = len(_FIELDS - result.keys())
    invalid = 0
    unknown = len(set(result) - _FIELDS)
    data: dict[str, object] = {}
    for field, output in _OUTPUTS.items():
        if field not in result:
            continue
        value = result[field]
        if type(value) is int and 0 <= value < 2 ** 31:
            data[output] = value
        else:
            invalid += 1
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
