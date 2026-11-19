"""Allowlisted projection of the documented GatewayInfo response."""

from __future__ import annotations

import re
from collections.abc import Mapping


class GatewayInfoSummaryError(ValueError):
    """Raised when the response is not a bounded GatewayInfo object."""


_TEXT_FIELDS = {
    "showModel": "model",
    "firmwareVersion": "firmware_version",
}
_KNOWN_OMITTED_FIELDS = frozenset({
    "mac", "ip", "uptime", "temp", "cpuUtil", "memUtil", "ipv6List",
    "portConfigs", "multiChipGateway", "multiChipInfos",
})
_SAFE_TEXT = re.compile(r"[A-Za-z0-9._() /+:-]{1,96}")
_INT64_MIN = -(2 ** 63)
_INT64_MAX = 2 ** 63 - 1


def project_gateway_info(result: object) -> dict[str, object]:
    """Return only model, firmware version, and the unscaled last-seen value."""
    if not isinstance(result, Mapping) or len(result) > 32:
        raise GatewayInfoSummaryError("result must be a bounded object")

    data: dict[str, object] = {}
    missing = invalid = 0
    for source, target in _TEXT_FIELDS.items():
        value = result.get(source)
        if value is None:
            missing += 1
            data[target] = None
        elif not isinstance(value, str) or not _SAFE_TEXT.fullmatch(value):
            invalid += 1
            data[target] = None
        else:
            data[target] = value

    last_seen = result.get("lastSeen")
    if last_seen is None:
        missing += 1
        data["last_seen_source_value"] = None
    elif (type(last_seen) is not int or not _INT64_MIN <= last_seen <= _INT64_MAX):
        invalid += 1
        data["last_seen_source_value"] = None
    else:
        data["last_seen_source_value"] = last_seen

    known = frozenset((*_TEXT_FIELDS, "lastSeen")) | _KNOWN_OMITTED_FIELDS
    unknown = sum(not isinstance(key, str) or key not in known for key in result)
    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
