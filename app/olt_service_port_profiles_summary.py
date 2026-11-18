"""Redacted aggregate for the documented OLT service-port profile list."""
from __future__ import annotations

from typing import Any

MAX_PROFILES = 512
MAX_FIELDS = 8
MAX_ENTRIES = 127


class OltServicePortProfilesError(ValueError):
    """Raised for malformed or unbounded profile responses."""


def project_olt_service_port_profiles_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_PROFILES:
        raise OltServicePortProfilesError("response_invalid")
    missing = invalid = unknown = redacted = entries_reported = 0
    entries_total = 0
    in_use_reported = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > MAX_FIELDS:
            invalid += 1
            continue
        unknown += len(set(row) - {"servicePortProfileId", "servicePortProfileName",
                                  "entriesNumber", "inUse"})
        redacted += len(row)
        for field, max_length in (("servicePortProfileId", 32), ("servicePortProfileName", 32)):
            value = row.get(field)
            if value is None:
                missing += 1
            elif not isinstance(value, str) or not value or len(value) > max_length:
                invalid += 1
        entries = row.get("entriesNumber")
        if entries is None:
            missing += 1
        elif type(entries) is int and 0 <= entries <= MAX_ENTRIES:
            entries_total += entries
            entries_reported += 1
        else:
            invalid += 1
        in_use = row.get("inUse")
        if in_use is None:
            missing += 1
        elif isinstance(in_use, str) and len(in_use) <= 32:
            in_use_reported += 1
        else:
            invalid += 1
    return {
        "data": {"profile_count": len(result), "entries_total": entries_total,
                 "entries_number_reported_profile_count": entries_reported,
                 "in_use_reported_profile_count": in_use_reported},
        "partial": bool(missing or invalid or unknown),
        "missing_count": missing, "invalid_count": invalid,
        "unknown_field_count": unknown, "redacted_field_count": redacted,
    }
