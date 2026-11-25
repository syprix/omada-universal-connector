"""Redacted projection for controller-wide device and health counters."""
from __future__ import annotations

from typing import Any


FIELD_MAP = {
    "allDevices": "total_devices",
    "allSwitchsAndGateway": "switches_and_gateways",
    "allAps": "access_points",
    "allOlts": "olts",
    "mesh": "mesh_devices",
    "config": "config_devices",
    "performance": "performance_devices",
    "unActivated": "unactivated_devices",
    "activated": "activated_devices",
    "expired": "expired_devices",
    "good": "health_good",
    "fair": "health_fair",
    "poor": "health_poor",
    "noData": "health_no_data",
}
HEALTH_FIELD_MAP = {
    "switchHealth": "switches",
    "eapHealth": "access_points",
    "gatewayHealth": "gateways",
}
HEALTH_COUNT_FIELDS = ("good", "fair", "poor", "noData")
MAX_SOURCE_FIELDS = 32


class ControllerDeviceStatisticsError(ValueError):
    """Raised when the response is not a bounded object."""


def project_controller_device_statistics(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerDeviceStatisticsError("response_invalid")
    counts: dict[str, int] = {}
    invalid_count = 0
    for source, target in FIELD_MAP.items():
        if source not in result:
            continue
        value = result[source]
        if type(value) is int and 0 <= value <= 2_147_483_647:
            counts[target] = value
        else:
            invalid_count += 1
    health_counts: dict[str, dict[str, int]] = {}
    health_missing_count = 0
    health_invalid_count = 0
    omitted_variant_field_count = 0
    unknown_health_field_count = 0
    for source, target in HEALTH_FIELD_MAP.items():
        if source not in result:
            continue
        value = result[source]
        if not isinstance(value, dict) or len(value) > MAX_SOURCE_FIELDS:
            omitted_variant_field_count += 1
            continue
        projected: dict[str, int] = {}
        for field in HEALTH_COUNT_FIELDS:
            if field not in value:
                health_missing_count += 1
                continue
            counter = value[field]
            if type(counter) is int and 0 <= counter <= 2_147_483_647:
                projected[field] = counter
            else:
                health_invalid_count += 1
        unknown_health_field_count += len(set(value) - set(HEALTH_COUNT_FIELDS))
        if projected:
            health_counts[target] = projected
    missing_count = len(FIELD_MAP) - sum(field in result for field in FIELD_MAP)
    unknown_count = len(set(result) - set(FIELD_MAP) - set(HEALTH_FIELD_MAP))
    return {
        "data": {
            "counts": counts,
            "health_counts": health_counts,
            "present_count": len(counts),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "health_missing_count": health_missing_count,
            "health_invalid_count": health_invalid_count,
            "omitted_variant_field_count": omitted_variant_field_count,
            "unknown_field_count": unknown_count + unknown_health_field_count,
        },
        "partial": bool(missing_count or invalid_count or health_missing_count or health_invalid_count or
                         omitted_variant_field_count or unknown_count or unknown_health_field_count),
    }
