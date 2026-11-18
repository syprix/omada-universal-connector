"""Redacted projection for controller built-in RADIUS server settings."""
from __future__ import annotations

from typing import Any

KNOWN_FIELDS = {
    "enable", "authServerPort", "secret", "tunnelReplyEnable", "status",
    "failReason", "serverAddressType", "customAddress", "radiusServerCertificate",
    "requireMessageAuthenticator", "limitProxyState",
}
REQUIRED_FIELDS = {
    "enable", "authServerPort", "secret", "tunnelReplyEnable", "serverAddressType",
}
BOOLEAN_FIELDS = {
    "enable": "enabled",
    "tunnelReplyEnable": "tunnel_reply_enabled",
    "status": "running",
    "requireMessageAuthenticator": "require_message_authenticator",
    "limitProxyState": "limit_proxy_state",
}
CERTIFICATE_FIELDS = {"cerId", "cerName", "keyId", "keyName", "keyPassword", "cerType"}
MAX_SOURCE_FIELDS = 32
MAX_FAILURE_REASON_LENGTH = 512
MAX_CERTIFICATE_FIELDS = 12


class ControllerRadiusServerError(ValueError):
    """Raised when the response is not a bounded object."""


def _present_nonempty(value: object, max_length: int) -> bool | None:
    if not isinstance(value, str) or len(value) > max_length:
        return None
    return bool(value)


def project_controller_radius_server(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerRadiusServerError("response_invalid")

    settings: dict[str, object] = {}
    redacted_presence: dict[str, bool] = {}
    invalid_count = 0
    for source, target in BOOLEAN_FIELDS.items():
        if source not in result:
            continue
        value = result[source]
        if isinstance(value, bool):
            settings[target] = value
        else:
            invalid_count += 1

    if "authServerPort" in result:
        port = result["authServerPort"]
        if isinstance(port, int) and not isinstance(port, bool) and -(2**31) <= port < 2**31:
            settings["auth_server_port"] = port
        else:
            invalid_count += 1

    if "serverAddressType" in result:
        address_type = result["serverAddressType"]
        if (isinstance(address_type, int) and not isinstance(address_type, bool)
                and -(2**31) <= address_type < 2**31):
            settings["server_address_type"] = address_type
        else:
            invalid_count += 1

    if "secret" in result:
        present = _present_nonempty(result["secret"], MAX_FAILURE_REASON_LENGTH)
        if present is None:
            invalid_count += 1
        else:
            redacted_presence["secret"] = present

    if "failReason" in result:
        present = _present_nonempty(result["failReason"], MAX_FAILURE_REASON_LENGTH)
        if present is None:
            invalid_count += 1
        else:
            redacted_presence["failure_reason"] = present

    if "customAddress" in result:
        present = _present_nonempty(result["customAddress"], 253)
        if present is None:
            invalid_count += 1
        else:
            redacted_presence["custom_address"] = present

    if "radiusServerCertificate" in result:
        certificate = result["radiusServerCertificate"]
        if certificate is None:
            redacted_presence["certificate_configured"] = False
        elif not isinstance(certificate, dict) or len(certificate) > MAX_CERTIFICATE_FIELDS:
            invalid_count += 1
        else:
            redacted_presence["certificate_configured"] = any(
                bool(certificate.get(key)) for key in CERTIFICATE_FIELDS
                if isinstance(certificate.get(key), str)
            )
            invalid_count += sum(
                not isinstance(value, str) or len(value) > MAX_FAILURE_REASON_LENGTH
                for value in certificate.values()
            )
            unknown_certificate_fields = len(set(certificate) - CERTIFICATE_FIELDS)
            invalid_count += unknown_certificate_fields

    missing_required_count = sum(key not in result for key in REQUIRED_FIELDS)
    if result.get("status") is False and "failReason" not in result:
        missing_required_count += 1
    if (type(result.get("serverAddressType")) is int and
            result["serverAddressType"] == 1 and "customAddress" not in result):
        missing_required_count += 1
    unknown_field_count = len(set(result) - KNOWN_FIELDS)
    return {
        "data": {
            "settings": settings,
            "redacted_presence": redacted_presence,
            "present_count": len(settings) + len(redacted_presence),
            "missing_required_count": missing_required_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_field_count,
        },
        "partial": bool(missing_required_count or invalid_count or unknown_field_count),
    }
