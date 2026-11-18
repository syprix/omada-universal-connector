"""Redacted summaries for OLT ONU registration settings."""
from __future__ import annotations

from typing import Any


MAX_INT32 = 2_147_483_647
_AUTO_AUTH_FIELDS = {"autoAuthenticationStatus"}
_AUTOFIND_FIELDS = {"ponPort", "agingTimeStatus", "agingTime", "autofindInterval"}


class OltOnuRegistrationError(ValueError):
    """Raised when an ONU registration settings response is unbounded."""


def project_olt_onu_auto_auth_status(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise OltOnuRegistrationError("response_invalid")
    missing = 0
    invalid = 0
    unknown = len(set(result) - _AUTO_AUTH_FIELDS)
    redacted = 0
    data: dict[str, object] = {}
    status = result.get("autoAuthenticationStatus")
    if status is None:
        missing += 1
    elif isinstance(status, str) and status in {"DISABLE", "ENABLE"}:
        data["auto_authentication_enabled"] = status == "ENABLE"
        redacted += 1
    else:
        invalid += 1
    return {"data": data, "partial": bool(missing or invalid or unknown),
            "missing_count": missing, "invalid_count": invalid,
            "unknown_field_count": unknown, "redacted_field_count": redacted}


def project_olt_onu_autofind_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise OltOnuRegistrationError("response_invalid")
    missing = 0
    invalid = 0
    unknown = len(set(result) - _AUTOFIND_FIELDS)
    redacted = 0
    data: dict[str, object] = {}
    pon_ports = result.get("ponPort")
    if pon_ports is None:
        missing += 1
        data["pon_port_scope_configured"] = False
    elif isinstance(pon_ports, str) and len(pon_ports) <= 2048:
        data["pon_port_scope_configured"] = bool(pon_ports.strip())
        redacted += 1
    else:
        invalid += 1

    aging_status = result.get("agingTimeStatus")
    if aging_status is None:
        missing += 1
    elif isinstance(aging_status, str) and aging_status in {"TIMEOUT", "NO_AGING"}:
        data["aging_time_status"] = aging_status
        redacted += 1
    else:
        invalid += 1

    aging_time = result.get("agingTime")
    if aging_time is not None:
        if type(aging_time) is int and 0 <= aging_time <= MAX_INT32:
            data["aging_time_code"] = aging_time
            redacted += 1
        else:
            invalid += 1

    interval = result.get("autofindInterval")
    if interval is None:
        missing += 1
    elif type(interval) is int and 1 <= interval <= 10:
        data["autofind_interval_seconds"] = interval
        redacted += 1
    else:
        invalid += 1
    return {"data": data, "partial": bool(missing or invalid or unknown),
            "missing_count": missing, "invalid_count": invalid,
            "unknown_field_count": unknown, "redacted_field_count": redacted}
