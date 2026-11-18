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
KNOWN_VARIANT_FIELDS = {"switchHealth", "eapHealth", "gatewayHealth"}
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
    missing_count = len(FIELD_MAP) - sum(field in result for field in FIELD_MAP)
    variant_count = len(set(result) & KNOWN_VARIANT_FIELDS)
    unknown_count = len(set(result) - set(FIELD_MAP) - KNOWN_VARIANT_FIELDS)
    return {
        "data": {
            "counts": counts,
            "present_count": len(counts),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "omitted_variant_field_count": variant_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or variant_count or unknown_count),
    }
