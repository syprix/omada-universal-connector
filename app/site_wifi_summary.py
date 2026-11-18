"""Bounded projection of the documented site WLAN summary."""
from __future__ import annotations

import math


class SiteWifiSummaryError(ValueError):
    """The controller returned a malformed site WLAN summary."""


_INT_FIELDS = ("connectedApNum", "clients")
_FIELDS = frozenset({*_INT_FIELDS, "channelUtilization", "totalTraffic"})
_MAX_FIELDS = 16
_INT32_MAX = 2**31 - 1
_MAX_TRAFFIC_KB = 1e15


def project_site_wifi_summary(raw: object) -> dict[str, object]:
    """Project documented counts, average utilization and traffic in KB.

    Null utilization is preserved as the specification says it means no value.
    Traffic is reported as the controller's total KB measurement; no rate or
    interval normalization is inferred.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise SiteWifiSummaryError()
    if any(not isinstance(key, str) or len(key) > 128 for key in raw):
        raise SiteWifiSummaryError()

    data: dict[str, int | float | None] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for field in _INT_FIELDS:
        if field not in raw:
            missing.append(field)
            continue
        value = raw[field]
        if type(value) is int and 0 <= value <= _INT32_MAX:
            data[field] = value
        else:
            invalid.append(field)

    field = "channelUtilization"
    if field not in raw:
        missing.append(field)
    elif raw[field] is None:
        data[field] = None
    elif type(raw[field]) is int and 0 <= raw[field] <= 100:
        data[field] = raw[field]
    else:
        invalid.append(field)

    field = "totalTraffic"
    if field not in raw:
        missing.append(field)
    else:
        value = raw[field]
        if (type(value) in {int, float} and math.isfinite(value) and
                0 <= value <= _MAX_TRAFFIC_KB):
            data[field] = value
        else:
            invalid.append(field)

    unknown_count = sum(key not in _FIELDS for key in raw)
    return {
        "status": "ok",
        "resource": "site_wifi_summary",
        "data": data,
        "partial": bool(missing or invalid or unknown_count),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_count,
    }
