"""Redacted AP full-channel-detection status projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ApFullChannelDetectStatusError(ValueError):
    """The AP status response does not match its documented scalar schema."""


_STATUS_FIELDS = {
    "status": "full_channel_detection",
    "wifiInterfStatus": "wifi_interference",
    "interfStatus": "interference",
    "channelLoadStatus": "channel_load",
}
_STATUS_LABELS = {0: "unscanned_with_result", 1: "unscanned_without_result",
                  3: "scanning"}
_ALLOWED = frozenset((*_STATUS_FIELDS, "lastSeen", "fromGlobal"))
_INT64_MIN, _INT64_MAX = -(2**63), 2**63 - 1


def project_ap_full_channel_detect_status(value: Any) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 8:
        raise ApFullChannelDetectStatusError("result_invalid")
    unknown = sum(key not in _ALLOWED for key in value)
    invalid = missing = 0
    statuses: dict[str, str] = {}
    for source, target in _STATUS_FIELDS.items():
        if source not in value or value[source] is None:
            missing += 1
            continue
        code = value[source]
        if type(code) is not int or code not in _STATUS_LABELS:
            invalid += 1
            continue
        statuses[target] = _STATUS_LABELS[code]

    last_seen_present = False
    if "lastSeen" in value and value["lastSeen"] is not None:
        timestamp = value["lastSeen"]
        if type(timestamp) is not int or not _INT64_MIN <= timestamp <= _INT64_MAX:
            invalid += 1
        else:
            last_seen_present = True

    from_global = None
    if "fromGlobal" in value and value["fromGlobal"] is not None:
        if type(value["fromGlobal"]) is not bool:
            invalid += 1
        else:
            from_global = value["fromGlobal"]

    return {"data": {"statuses": statuses,
                     "last_seen_present": last_seen_present,
                     "from_global": from_global,
                     "missing_field_count": missing,
                     "invalid_field_count": invalid,
                     "unknown_field_count": unknown},
            "partial": bool(missing or invalid or unknown)}
