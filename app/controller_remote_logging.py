"""Redacted projection for controller remote logging settings."""
from __future__ import annotations

import ipaddress
import re
from typing import Any

KNOWN_FIELDS = {"enable", "host", "port"}
MAX_SOURCE_FIELDS = 16
_DOMAIN_HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,6}\Z"
)


class ControllerRemoteLoggingError(ValueError):
    """Raised when remote logging settings exceed the bounded source shape."""


def _valid_host(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 253:
        return False
    try:
        ipaddress.IPv4Address(value)
        return True
    except ipaddress.AddressValueError:
        return bool(_DOMAIN_HOST.fullmatch(value))


def project_controller_remote_logging(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerRemoteLoggingError("response_invalid")

    settings: dict[str, object] = {}
    invalid_count = 0
    missing_required_count = 0

    if "enable" not in result:
        missing_required_count = 1
    elif isinstance(result["enable"], bool):
        settings["enabled"] = result["enable"]
    else:
        invalid_count += 1

    if "host" in result:
        host = result["host"]
        if host == "":
            settings["host_present"] = False
        elif _valid_host(host):
            settings["host_present"] = True
        else:
            settings["host_present"] = False
            invalid_count += 1
    else:
        settings["host_present"] = False

    if "port" in result:
        port = result["port"]
        if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535:
            settings["port_present"] = True
        else:
            settings["port_present"] = False
            invalid_count += 1
    else:
        settings["port_present"] = False

    unknown_count = len(set(result) - KNOWN_FIELDS)
    return {
        "data": {
            "settings": settings,
            "present_count": len(settings),
            "missing_required_count": missing_required_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_required_count or invalid_count or unknown_count),
    }
