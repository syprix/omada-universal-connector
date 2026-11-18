"""Bounded projection for controller daylight-saving-time information."""
from __future__ import annotations

from typing import Any

BOOLEAN_FIELDS = {"enable", "status"}
TIMESTAMP_FIELDS = {"startTime", "endTime", "nextStart", "nextEnd", "lastStart", "lastEnd"}
KNOWN_FIELDS = BOOLEAN_FIELDS | TIMESTAMP_FIELDS | {"mode", "offset", "timeZone", "start", "end"}
MAX_SOURCE_FIELDS = 16
MAX_TIME_ZONE_LENGTH = 128
OFFSET_VALUES = {1_800_000, 3_600_000, 5_400_000, 7_200_000}
TIME_FIELDS = {
    "month": (1, 12),
    "serial": (1, 5),
    "day": (1, 7),
    "hour": (0, 23),
    "minute": (0, 59),
}


class ControllerDstError(ValueError):
    """Raised when the DST response is not a bounded object."""


def _time_rule(value: Any) -> tuple[dict[str, int] | None, int]:
    if not isinstance(value, dict) or len(value) > len(TIME_FIELDS):
        return None, 1
    projected: dict[str, int] = {}
    invalid = 0
    for name, (minimum, maximum) in TIME_FIELDS.items():
        if name not in value:
            invalid += 1
            continue
        item = value[name]
        if type(item) is int and minimum <= item <= maximum:
            projected[name] = item
        else:
            invalid += 1
    if invalid:
        return projected or None, invalid
    return projected, 0


def project_controller_dst(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerDstError("response_invalid")
    settings: dict[str, object] = {}
    timestamp_values: dict[str, int] = {}
    invalid_count = 0
    for name in BOOLEAN_FIELDS:
        if name not in result:
            continue
        value = result[name]
        if type(value) is bool:
            settings["enabled" if name == "enable" else "available"] = value
        else:
            invalid_count += 1
    if "mode" in result:
        value = result["mode"]
        if type(value) is int and 0 <= value <= 2:
            settings["mode_code"] = value
        else:
            invalid_count += 1
    if "offset" in result:
        value = result["offset"]
        if type(value) is int and value in OFFSET_VALUES:
            settings["offset_ms"] = value
        else:
            invalid_count += 1
    if "timeZone" in result:
        value = result["timeZone"]
        if isinstance(value, str) and len(value) <= MAX_TIME_ZONE_LENGTH:
            settings["time_zone"] = value
        else:
            invalid_count += 1
    time_rules: dict[str, dict[str, int]] = {}
    for source, target in (("start", "start_rule"), ("end", "end_rule")):
        if source not in result:
            continue
        projected, invalid = _time_rule(result[source])
        invalid_count += invalid
        if projected:
            time_rules[target] = projected
    for source in TIMESTAMP_FIELDS:
        if source not in result:
            continue
        value = result[source]
        if type(value) is int and -(2**63) <= value <= 2**63 - 1:
            timestamp_values[source[0].lower() + source[1:]] = value
        else:
            invalid_count += 1
    missing_count = len(KNOWN_FIELDS) - sum(name in result for name in KNOWN_FIELDS)
    enabled = result.get("enable")
    disabled_and_sparse = type(enabled) is bool and not enabled
    partial = bool(invalid_count or (missing_count and not disabled_and_sparse))
    return {
        "data": {
            "settings": settings,
            "time_rules": time_rules,
            "timestamps_ms": timestamp_values,
            "present_count": len(settings) + sum(len(rule) for rule in time_rules.values()) + len(timestamp_values),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": len(set(result) - KNOWN_FIELDS),
        },
        "partial": partial or bool(set(result) - KNOWN_FIELDS),
    }
