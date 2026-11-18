"""Validation and projection for the documented longest-uptime dashboard read."""
from __future__ import annotations

from collections.abc import Mapping


class LongestClientUptimeError(ValueError):
    """The documented client-summary response is malformed."""


_FIELDS = frozenset(("total", "wiredClient", "wirelessClient"))


def summarize_longest_client_uptime(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 16:
        raise LongestClientUptimeError("invalid longest-uptime response")
    values: dict[str, int | None] = {}
    invalid = missing = 0
    for source in ("total", "wiredClient", "wirelessClient"):
        item = value.get(source)
        if source not in value:
            missing += 1
            values[source] = None
        elif type(item) is int and -2_147_483_648 <= item <= 2_147_483_647:
            values[source] = item
        else:
            invalid += 1
            values[source] = None
    unknown = sum(key not in _FIELDS for key in value)
    return {
        "status": "ok",
        "resource": "site_longest_client_uptime_summary",
        **values,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
