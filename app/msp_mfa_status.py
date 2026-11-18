"""Bounded projection for the MSP multi-factor authentication status."""
from __future__ import annotations

from typing import Any


class MspMfaStatusError(ValueError):
    """Raised when the documented MFA status shape is invalid."""


def project_msp_mfa_status(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise MspMfaStatusError("response_invalid")
    value = result.get("enable")
    valid = type(value) is bool
    return {
        "data": {"enabled": value if valid else None,
                 "invalid_count": int("enable" in result and not valid),
                 "unknown_field_count": len(set(result) - {"enable"})},
        "partial": not valid or any(key != "enable" for key in result),
    }
