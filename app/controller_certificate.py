"""Redacted projection for the configured controller certificate."""
from __future__ import annotations

from typing import Any

KNOWN_FIELDS = {
    "cerId", "cerName", "keyName", "keyId", "enable", "keyPassword",
    "trustPassword", "cerType",
}
REQUIRED_FIELDS = {"cerId"}
MAX_SOURCE_FIELDS = len(KNOWN_FIELDS)
MAX_TEXT_LENGTH = 4096


class ControllerCertificateError(ValueError):
    """Raised when a certificate response is not a bounded object."""


def project_controller_certificate(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerCertificateError("response_invalid")
    presence: dict[str, bool] = {}
    enabled: bool | None = None
    invalid = 0
    for field in ("cerId", "cerName", "keyName", "keyId", "keyPassword",
                  "trustPassword", "cerType"):
        if field not in result:
            continue
        value = result[field]
        if isinstance(value, str) and len(value) <= MAX_TEXT_LENGTH and value.isprintable():
            presence[field] = bool(value.strip())
        else:
            invalid += 1
    if "enable" in result:
        if type(result["enable"]) is bool:
            enabled = result["enable"]
        else:
            invalid += 1
    missing = len(KNOWN_FIELDS - result.keys())
    required_missing = len(REQUIRED_FIELDS - result.keys())
    unknown = len(result.keys() - KNOWN_FIELDS)
    return {
        "data": {"enabled": enabled, "field_presence": presence,
                 "present_count": len(presence) + int(enabled is not None),
                 "missing_count": missing, "required_missing_count": required_missing,
                 "invalid_count": invalid, "unknown_field_count": unknown},
        "partial": bool(missing or invalid or unknown),
    }
