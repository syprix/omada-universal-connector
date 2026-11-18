"""Bounded projection for MSP license auto-activation status."""
from __future__ import annotations

from typing import Any


class MspLicenseAutoActiveError(ValueError):
    """Raised when the documented auto-activation result is invalid."""


def project_msp_license_auto_active(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise MspLicenseAutoActiveError("response_invalid")
    value = result.get("autoActive")
    valid = type(value) is bool
    return {
        "data": {"enabled": value if valid else None,
                 "invalid_count": int("autoActive" in result and not valid),
                 "unknown_field_count": len(set(result) - {"autoActive"})},
        "partial": not valid or any(key != "autoActive" for key in result),
    }
