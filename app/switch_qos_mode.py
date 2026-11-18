"""Bounded read-only projection for the documented site switch QoS mode."""
from __future__ import annotations

from typing import Any


class SwitchQosModeError(ValueError):
    """Raised for an invalid switch QoS mode response."""


def project_switch_qos_mode(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SwitchQosModeError("response_invalid")
    data: dict[str, object] = {}
    missing = invalid = 0
    if "qosMode" not in result:
        missing += 1
    elif type(result["qosMode"]) is int and result["qosMode"] in (0, 1):
        data["mode"] = {0: "profile_based", 1: "rules_based"}[result["qosMode"]]
    else:
        invalid += 1
    if "completed" not in result:
        missing += 1
    elif type(result["completed"]) is int and result["completed"] in (0, 1):
        data["transition_completed"] = bool(result["completed"])
    else:
        invalid += 1
    unknown = len(set(result) - {"qosMode", "completed"})
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
