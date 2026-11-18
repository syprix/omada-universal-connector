"""Projection for controller client-detail data settings."""
from __future__ import annotations

from typing import Any

BOOLEAN_FIELDS = {
    "clientRecognitionEnable", "clientHealthEnable", "clientHistoryEnable",
    "clientDataTrendEnable", "followMsp",
}
MSP_BOOLEAN_FIELDS = {
    "clientHealthEnable", "clientHistoryEnable", "clientDataTrendEnable",
}


class ControllerClientDetailInfoError(ValueError):
    """Raised when the documented response is not a bounded object."""


def _target(name: str) -> str:
    output = []
    for char in name:
        if char.isupper():
            output.extend(("_", char.lower()))
        else:
            output.append(char)
    return "".join(output).lstrip("_")


def project_controller_client_detail_info(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 12:
        raise ControllerClientDetailInfoError("response_invalid")
    flags: dict[str, bool] = {}
    invalid_count = 0
    for source in BOOLEAN_FIELDS:
        if source not in result:
            continue
        value = result[source]
        if type(value) is bool:
            flags[_target(source)] = value
        else:
            invalid_count += 1
    missing_count = sum(source not in result for source in BOOLEAN_FIELDS)
    unknown_count = len(set(result) - BOOLEAN_FIELDS)
    return {
        "data": {
            "settings": flags,
            "present_count": len(flags),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }


def project_msp_client_detail_info(result: Any) -> dict[str, object]:
    """Project only the three fields defined by the MSP result schema."""
    if not isinstance(result, dict) or len(result) > 8:
        raise ControllerClientDetailInfoError("response_invalid")
    flags: dict[str, bool] = {}
    invalid_count = 0
    for source in MSP_BOOLEAN_FIELDS:
        if source not in result:
            continue
        value = result[source]
        if type(value) is bool:
            flags[_target(source)] = value
        else:
            invalid_count += 1
    missing_count = sum(source not in result for source in MSP_BOOLEAN_FIELDS)
    unknown_count = len(set(result) - MSP_BOOLEAN_FIELDS)
    return {
        "data": {
            "settings": flags,
            "present_count": len(flags),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
