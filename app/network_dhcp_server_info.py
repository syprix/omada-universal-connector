"""Redacted projection for a network's DHCP address-pool summary."""
from __future__ import annotations

from typing import Any

MAX_RANGES = 64
MAX_SOURCE_FIELDS = 16
MAX_ADDRESS_LENGTH = 64


class NetworkDhcpServerInfoError(ValueError):
    """Raised when the DHCP pool response exceeds safe projection bounds."""


def project_network_dhcp_server_info(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise NetworkDhcpServerInfoError("response_invalid")

    raw_ranges = result.get("ranges")
    if raw_ranges is None:
        raw_ranges = []
        missing_ranges = 1
    elif not isinstance(raw_ranges, list):
        raise NetworkDhcpServerInfoError("response_invalid")
    else:
        missing_ranges = 0

    included = raw_ranges[:MAX_RANGES]
    omitted = len(raw_ranges) - len(included)
    available = 0
    valid_available_count = 0
    invalid_range_count = 0
    unknown_field_count = len(set(result) - {"ranges"})

    for row in included:
        if not isinstance(row, dict) or len(row) > MAX_SOURCE_FIELDS:
            invalid_range_count += 1
            continue
        unknown_field_count += len(set(row) - {"startIp", "endIp", "availableIpNum"})
        invalid = False
        for key in ("startIp", "endIp"):
            value = row.get(key)
            if not isinstance(value, str) or len(value) > MAX_ADDRESS_LENGTH:
                invalid = True
        value = row.get("availableIpNum")
        if type(value) is int and 0 <= value <= 2_147_483_647:
            available += value
            valid_available_count += 1
        else:
            invalid = True
        if invalid:
            invalid_range_count += 1

    partial = bool(missing_ranges or invalid_range_count or unknown_field_count or omitted)
    return {
        "data": {
            "range_count": len(raw_ranges),
            "included_range_count": len(included),
            "omitted_range_count": omitted,
            "available_ip_count": available,
            "available_ip_values_count": valid_available_count,
            "invalid_range_count": invalid_range_count,
            "unknown_field_count": unknown_field_count,
            "missing_ranges_count": missing_ranges,
        },
        "partial": partial,
    }
