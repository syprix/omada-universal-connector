"""Strict summary for the documented site SSH settings GET."""
from __future__ import annotations

from typing import Any

class SiteSshSummaryError(ValueError):
    """Raised when the SSH setting cannot be projected safely."""

def summarize_site_ssh(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        raise SiteSshSummaryError("response_invalid")
    allowed = {"sshEnable", "sshServerPort", "layer3Access"}
    unknown = len(set(result) - allowed)
    missing = invalid = 0
    enabled_raw = result.get("sshEnable")
    if type(enabled_raw) is bool:
        enabled: bool | None = enabled_raw
    else:
        enabled = None
        if "sshEnable" not in result:
            missing += 1
        else:
            invalid += 1
    layer3_raw = result.get("layer3Access")
    if type(layer3_raw) is bool:
        layer3: bool | None = layer3_raw
    else:
        layer3 = None
        if "layer3Access" not in result:
            missing += 1
        else:
            invalid += 1
    port_raw = result.get("sshServerPort")
    if type(port_raw) is int and (port_raw == 22 or 1025 <= port_raw <= 65535):
        port: int | None = port_raw
    else:
        port = None
        if "sshServerPort" not in result:
            missing += 1
        else:
            invalid += 1
    return {"data": {"enabled": enabled, "layer3_access_enabled": layer3,
                     "server_port": port},
            "missing_field_count": missing, "invalid_field_count": invalid,
            "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
