"""Redacted projection of documented AP antenna switch settings."""
from __future__ import annotations


class ApAntennaError(ValueError):
    """The AP antenna result cannot be bounded or projected safely."""

    def __init__(self, code: str = "ap_antenna_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_BANDS = ("2g", "5g", "5g2", "6g")
_SETTING_FIELDS = ("antMode", "antGain", "antPattern", "customGainLimit", "defaultOmniGain")
_TOP_FIELDS = ("antMode", "omniAntState") + tuple(f"antSetting{band}" for band in _BANDS)
_MAX_FIELDS = 16
_MAX_KEY_LENGTH = 128
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def _top_valid(field: str, value: object) -> bool:
    if not _int32(value):
        return False
    if field == "antMode":
        return value in (0, 1, 2, 3)
    return value in (0, 1, 2)


def project_ap_antenna(raw: object) -> dict[str, object]:
    """Project only documented global and per-band antenna fields.

    Global ``antMode`` and ``omniAntState`` use their documented enums. Nested
    integer fields are checked as int32; only ``antPattern`` has the documented
    0/1 restriction. No other numeric range or hardware/firmware cause is
    inferred. Missing, invalid, and unknown fields mark the result partial.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise ApAntennaError()

    data: dict[str, int | dict[str, int]] = {}
    missing: list[str] = []
    invalid: list[str] = []
    unknown_field_count = 0

    for field in ("antMode", "omniAntState"):
        if field not in raw:
            missing.append(field)
            continue
        if _top_valid(field, raw[field]):
            data[field] = raw[field]
        else:
            invalid.append(field)

    for band in _BANDS:
        field = f"antSetting{band}"
        if field not in raw:
            missing.append(field)
            continue
        source = raw[field]
        if not isinstance(source, dict):
            invalid.append(field)
            continue
        if len(source) > _MAX_FIELDS:
            raise ApAntennaError()
        projected: dict[str, int] = {}
        for nested_field in _SETTING_FIELDS:
            path = f"{field}.{nested_field}"
            if nested_field not in source:
                missing.append(path)
                continue
            value = source[nested_field]
            valid = _int32(value)
            if nested_field == "antPattern":
                valid = valid and value in (0, 1)
            if valid:
                projected[nested_field] = value
            else:
                invalid.append(path)
        extras = sum(1 for key in source if key not in _SETTING_FIELDS)
        unknown_field_count += extras
        data[field] = projected

    for key in raw:
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise ApAntennaError()
        if key not in _TOP_FIELDS:
            unknown_field_count += 1

    return {
        "status": "ok",
        "resource": "ap_antenna",
        "data": data,
        "partial": bool(missing or invalid or unknown_field_count),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_field_count,
    }
