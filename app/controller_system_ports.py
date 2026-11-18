"""Bounded, redacted projections for documented controller port settings."""
from __future__ import annotations

from typing import Any

_FIELDS: dict[str, dict[str, tuple[str, Any]]] = {
    "controller_upgrade_port": {
        "upgradeHttpsPort": ("upgrade_https_port", "port"),
    },
    "controller_port_settings": {
        "manageHttpPort": ("http_port", (80,)),
        "manageHttpsPort": ("https_port", (443,)),
        "hostName": ("host_name_present", "presence"),
        "autoRefresh": ("auto_refresh", "bool"),
    },
    "controller_portal_port_settings": {
        "portalHttpPort": ("http_port", (80,)),
        "portalHttpsPort": ("https_port", ()),
        "portalHost": ("portal_host_present", "presence"),
        "autoPortalIpEnable": ("auto_portal_ip_enabled", "bool"),
        "portalHttpsRedirect": ("https_redirect_enabled", "bool"),
    },
}

_MAX_FIELDS = 32
_MAX_HOST_LENGTH = 253


class ControllerSystemPortsError(ValueError):
    """Raised when a controller port settings response exceeds safe bounds."""


def project_controller_system_ports(result: Any, operation_id: str) -> dict[str, object]:
    fields = _FIELDS.get(operation_id)
    if fields is None or not isinstance(result, dict) or len(result) > _MAX_FIELDS:
        raise ControllerSystemPortsError("response_invalid")

    settings: dict[str, object] = {}
    invalid_count = 0
    for source, (target, rule) in fields.items():
        if source not in result:
            continue
        value = result[source]
        if rule == "port":
            valid = type(value) is int and 1024 <= value <= 65535
        elif rule == "bool":
            valid = type(value) is bool
        elif rule == "presence":
            valid = (isinstance(value, str) and len(value) <= _MAX_HOST_LENGTH and
                     not any(ord(char) < 32 or ord(char) == 127 for char in value))
            if valid:
                settings[target] = bool(value.strip())
        elif isinstance(rule, tuple):
            valid = (type(value) is int and
                     (1024 <= value <= 65535 or value in rule))
        else:
            valid = False
        if not valid:
            invalid_count += 1
        elif rule == "bool" or rule == "port" or isinstance(rule, tuple):
            settings[target] = value

    missing_count = sum(source not in result for source in fields)
    unknown_count = len(set(result) - set(fields))
    return {
        "data": {
            "settings": settings,
            "present_count": len(settings),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
