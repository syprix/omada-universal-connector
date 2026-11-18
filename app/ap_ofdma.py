"""Redacted projection and conservative write-readiness gate for AP OFDMA state."""
from __future__ import annotations


class ApOfdmaError(ValueError):
    """The documented OFDMA result cannot be bounded or projected safely."""

    def __init__(self, code: str = "ap_ofdma_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_BANDS = ("2g", "5g", "5g2", "6g")
_FIELDS = tuple(f"ofdmaEnable{band}" for band in _BANDS) + tuple(
    f"supportOfdma{band}" for band in _BANDS
)
_MAX_FIELDS = 32
_MAX_KEY_LENGTH = 128


def project_ap_ofdma(raw: object) -> dict[str, object]:
    """Project only the eight optional documented Boolean fields.

    Absent, invalid, and unknown values make the result partial. Unknown keys
    and their values are never copied. The ``supportOfdma*`` booleans are
    returned as documented; they do not establish a hardware or firmware cause.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise ApOfdmaError()

    data: dict[str, bool] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for field in _FIELDS:
        if field not in raw:
            missing.append(field)
        elif type(raw[field]) is bool:
            data[field] = raw[field]
        else:
            invalid.append(field)

    unknown_count = 0
    for key in raw:
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise ApOfdmaError()
        if key not in _FIELDS:
            unknown_count += 1

    partial = bool(missing or invalid or unknown_count)
    return {
        "status": "ok",
        "resource": "ap_ofdma",
        "data": data,
        "partial": partial,
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_count,
    }


def can_write_ofdma_band(projection: object, band: str) -> bool:
    """Return true only for complete state and explicit support for one band.

    This is a read-side precondition for a future write path; it performs no
    write and does not infer hardware or firmware compatibility.
    """
    if not isinstance(projection, dict) or band not in _BANDS:
        return False
    if (projection.get("status") != "ok" or projection.get("resource") != "ap_ofdma" or
            projection.get("partial") is not False):
        return False
    data = projection.get("data")
    if not isinstance(data, dict) or set(data) != set(_FIELDS):
        return False
    if any(type(data.get(field)) is not bool for field in _FIELDS):
        return False
    return data[f"supportOfdma{band}"] is True
