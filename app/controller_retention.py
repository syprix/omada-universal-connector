"""Bounded projection for controller history-retention settings."""
from __future__ import annotations

import re
from typing import Any

BOOLEAN_FIELDS = {
    "override", "clientsDataEnable", "clientDataTrendEnable",
    "clientRecognitionEnable", "clientHealthEnable",
}
INTEGER_FIELDS = {
    "knownClient", "clientHistory", "fiveMin", "tenMin", "hourly",
    "daily", "weekly", "portalAuth", "log", "rogueAp", "widsData",
    "clientDataTrendDaily",
}
ARRAY_FIELDS = {
    "knownClientAvailableRetentionDays", "clientHistoryAvailableRetentionDays",
    "dailyAvailableRetentionDays", "weeklyAvailableRetentionDays",
    "portalAuthAvailableRetentionDays", "logAvailableRetentionDays",
    "clientTrendAvailableRetentionDays",
}
KNOWN_FIELDS = BOOLEAN_FIELDS | INTEGER_FIELDS | ARRAY_FIELDS
REQUIRED_FIELDS = {"clientsDataEnable"}
MAX_SOURCE_FIELDS = 32
MAX_ARRAY_ITEMS = 64


class ControllerRetentionError(ValueError):
    """Raised when the controller response exceeds its documented bounds."""


def _target(source: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", source).lower()


def project_controller_retention(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerRetentionError("response_invalid")
    flags: dict[str, bool] = {}
    values: dict[str, object] = {}
    invalid_count = 0
    for source in BOOLEAN_FIELDS:
        if source not in result:
            continue
        value = result[source]
        if type(value) is bool:
            flags[_target(source)] = value
        else:
            invalid_count += 1
    for source in INTEGER_FIELDS:
        if source not in result:
            continue
        value = result[source]
        if type(value) is int and -(2**31) <= value <= 2**31 - 1:
            values[_target(source)] = value
        else:
            invalid_count += 1
    for source in ARRAY_FIELDS:
        if source not in result:
            continue
        raw = result[source]
        if not isinstance(raw, list) or len(raw) > MAX_ARRAY_ITEMS:
            invalid_count += 1
            continue
        valid: list[int] = []
        for value in raw:
            if type(value) is int and -(2**31) <= value <= 2**31 - 1:
                valid.append(value)
            else:
                invalid_count += 1
        values[_target(source)] = valid
    missing_count = sum(source not in result for source in KNOWN_FIELDS)
    required_missing = sum(source not in result for source in REQUIRED_FIELDS)
    unknown_count = len(set(result) - KNOWN_FIELDS)
    return {
        "data": {
            "flags": flags,
            "retention_values": values,
            "present_count": len(flags) + len(values),
            "missing_count": missing_count,
            "required_missing_count": required_missing,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
