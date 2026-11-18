"""Bounded projection for the documented unresolved-incident count."""
from __future__ import annotations

from typing import Any


MAX_SOURCE_FIELDS = 32
MAX_INT32 = 2_147_483_647


class SiteUnresolvedIncidentCountError(ValueError):
    """Raised when the response envelope exceeds the bounded projection."""


def project_site_unresolved_incident_count(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise SiteUnresolvedIncidentCountError("response_invalid")

    present = "activeNum" in result
    value = result.get("activeNum")
    valid = type(value) is int and 0 <= value <= MAX_INT32
    unknown_count = len(set(result) - {"activeNum"})
    missing_count = 0 if present else 1
    invalid_count = 1 if present and not valid else 0

    return {
        "data": {
            "unresolved_count": value if valid else None,
            "present": present and valid,
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
