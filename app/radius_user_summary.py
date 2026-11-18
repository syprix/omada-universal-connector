"""Redacted summary for site built-in RADIUS users."""
from __future__ import annotations

from typing import Any


_FIELDS = {
    "userId", "type", "username", "password", "upRateLimit", "downRateLimit",
    "upLimit", "downLimit", "vlanId", "timeout", "description",
}
_INT_FIELDS = {
    "type": 32, "upRateLimit": 64, "downRateLimit": 64,
    "upLimit": 64, "downLimit": 64, "vlanId": 32, "timeout": 32,
}
_STRING_LIMITS = {"userId": 128, "username": 128, "password": 1024, "description": 512}
MAX_ROWS = 10_000
MAX_ROW_FIELDS = 32


class RadiusUserSummaryError(ValueError):
    """Raised when the user inventory cannot be safely summarized."""


def _valid_int(value: object, bits: int) -> bool:
    return (type(value) is int and -(2 ** (bits - 1)) <= value < 2 ** (bits - 1))


def summarize_radius_users(rows: Any) -> dict[str, object]:
    """Return aggregate documented values; never return usernames or secrets."""
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise RadiusUserSummaryError("response_invalid")

    type_counts: dict[str, int] = {}
    counts = {
        "username_present": 0,
        "password_present": 0,
        "vlan_id_field_present": 0,
        "session_timeout_field_present": 0,
        "upload_rate_limit_field_present": 0,
        "download_rate_limit_field_present": 0,
        "upload_traffic_limit_field_present": 0,
        "download_traffic_limit_field_present": 0,
    }
    invalid_count = 0
    unknown_field_count = 0

    for row in rows:
        if not isinstance(row, dict) or len(row) > MAX_ROW_FIELDS:
            raise RadiusUserSummaryError("response_invalid")
        unknown_field_count += len(set(row) - _FIELDS)
        valid: dict[str, object] = {}
        for name, bits in _INT_FIELDS.items():
            if name not in row:
                continue
            value = row[name]
            if _valid_int(value, bits):
                valid[name] = value
            else:
                invalid_count += 1
        for name, maximum in _STRING_LIMITS.items():
            if name not in row:
                continue
            value = row[name]
            if isinstance(value, str) and len(value) <= maximum:
                valid[name] = value
            else:
                invalid_count += 1

        if "type" in valid:
            key = str(valid["type"])
            type_counts[key] = type_counts.get(key, 0) + 1
        for field, target in (
            ("username", "username_present"), ("password", "password_present"),
            ("vlanId", "vlan_id_field_present"), ("timeout", "session_timeout_field_present"),
            ("upRateLimit", "upload_rate_limit_field_present"),
            ("downRateLimit", "download_rate_limit_field_present"),
            ("upLimit", "upload_traffic_limit_field_present"),
            ("downLimit", "download_traffic_limit_field_present"),
        ):
            if field in valid and (field not in _STRING_LIMITS or bool(valid[field])):
                counts[target] += 1

    return {
        "data": {
            "user_count": len(rows),
            "user_type_code_counts": dict(sorted(type_counts.items(), key=lambda pair: int(pair[0]))),
            **counts,
            "invalid_field_count": invalid_count,
            "unknown_field_count": unknown_field_count,
        },
        "partial": bool(invalid_count or unknown_field_count),
    }
