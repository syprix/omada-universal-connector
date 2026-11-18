"""Redacted summary for controller cloud access status."""
from __future__ import annotations

from typing import Any


class ControllerCloudAccessError(ValueError):
    """Raised when controller cloud access status is invalid."""


def project_controller_cloud_access(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 16:
        raise ControllerCloudAccessError("response_invalid")

    data: dict[str, object] = {}
    invalid = 0
    missing = 0
    unknown = len(set(result) - {"enable", "owner", "status"})

    enabled = result.get("enable")
    if isinstance(enabled, bool):
        data["enabled"] = enabled
    elif "enable" in result:
        invalid += 1
    else:
        missing += 1

    status = result.get("status")
    if type(status) is int and status in {-1, 0, 1}:
        data["connection"] = {-1: "disabled", 0: "disconnected", 1: "connected"}[status]
    elif "status" in result:
        invalid += 1
    else:
        missing += 1

    owner = result.get("owner")
    if owner is not None:
        if isinstance(owner, str) and len(owner) <= 512:
            data["owner_present"] = bool(owner)
        else:
            invalid += 1

    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
