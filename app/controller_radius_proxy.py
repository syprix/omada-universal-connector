"""Redacted projection for controller-wide RADIUS proxy settings."""
from __future__ import annotations

from typing import Any

KNOWN_FIELDS = {
    "enable", "port", "status", "failReason",
    "requireMessageAuthenticator", "limitProxyState",
}
REQUIRED_FIELDS = {"enable", "port"}
BOOLEAN_FIELDS = {
    "enable": "enabled",
    "status": "running",
    "requireMessageAuthenticator": "require_message_authenticator",
    "limitProxyState": "limit_proxy_state",
}
MAX_SOURCE_FIELDS = 24
MAX_FAILURE_REASON_LENGTH = 512


class ControllerRadiusProxyError(ValueError):
    """Raised when the response is not a bounded object."""


def project_controller_radius_proxy(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerRadiusProxyError("response_invalid")

    settings: dict[str, object] = {}
    invalid_count = 0
    for source, target in BOOLEAN_FIELDS.items():
        if source not in result:
            continue
        value = result[source]
        if isinstance(value, bool):
            settings[target] = value
        else:
            invalid_count += 1

    if "port" in result:
        port = result["port"]
        if isinstance(port, int) and not isinstance(port, bool) and -(2**31) <= port < 2**31:
            settings["port"] = port
        else:
            invalid_count += 1

    if "failReason" in result:
        reason = result["failReason"]
        if isinstance(reason, str) and len(reason) <= MAX_FAILURE_REASON_LENGTH:
            settings["failure_reason_present"] = bool(reason)
        else:
            settings["failure_reason_present"] = False
            invalid_count += 1

    missing_required_count = sum(key not in result for key in REQUIRED_FIELDS)
    if result.get("status") is False and "failReason" not in result:
        missing_required_count += 1
    unknown_field_count = len(set(result) - KNOWN_FIELDS)
    return {
        "data": {
            "settings": settings,
            "present_count": len(settings),
            "missing_required_count": missing_required_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_field_count,
        },
        "partial": bool(missing_required_count or invalid_count or unknown_field_count),
    }
