"""Projection for controller client-history retention flags."""
from __future__ import annotations

from typing import Any


FIELDS = {
    "clientsDataEnable": "client_history_enabled",
    "clientStatEnable": "client_trend_enabled",
}


class ControllerClientHistoryRetentionError(ValueError):
    """Raised when the controller response cannot be safely projected."""


def project_controller_client_history_retention(result: Any) -> dict[str, object]:
    """Keep only the two documented booleans and report incomplete responses."""
    if not isinstance(result, dict) or len(result) > 16:
        raise ControllerClientHistoryRetentionError("response_invalid")

    data: dict[str, object] = {}
    invalid_count = 0
    missing_count = 0
    for source, target in FIELDS.items():
        if source not in result:
            missing_count += 1
        elif type(result[source]) is bool:
            data[target] = result[source]
        else:
            invalid_count += 1

    unknown_field_count = len(set(result) - set(FIELDS))
    data.update({
        "present_count": len(data),
        "missing_count": missing_count,
        "invalid_count": invalid_count,
        "unknown_field_count": unknown_field_count,
    })
    return {
        "data": data,
        "partial": bool(missing_count or invalid_count or unknown_field_count),
    }
