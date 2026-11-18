"""Redacted projection of the documented AP trunk-setting (LAG) result."""
from __future__ import annotations


class ApLagError(ValueError):
    """The documented AP LAG result cannot be bounded or projected safely."""

    def __init__(self, code: str = "ap_lag_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_FIELDS = ("supportTrunkSetting", "enable", "mode")
_BOOL_FIELDS = frozenset({"supportTrunkSetting", "enable"})
_MAX_FIELDS = 16
_MAX_KEY_LENGTH = 128
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def project_ap_lag(raw: object) -> dict[str, object]:
    """Project the three documented values without assigning extra semantics.

    Missing, invalid, or unknown fields mark the projection partial. Unknown
    names and values are never returned. ``supportTrunkSetting`` is the
    controller's reported flag; it does not establish a hardware or firmware
    cause. The integer mode is returned unchanged and is not translated.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise ApLagError()

    data: dict[str, bool | int] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for field in _FIELDS:
        if field not in raw:
            missing.append(field)
            continue
        value = raw[field]
        if field in _BOOL_FIELDS:
            if type(value) is bool:
                data[field] = value
            else:
                invalid.append(field)
        elif type(value) is int and _INT32_MIN <= value <= _INT32_MAX and value in (0, 1, 2):
            data[field] = value
        else:
            invalid.append(field)

    unknown_count = 0
    for key in raw:
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise ApLagError()
        if key not in _FIELDS:
            unknown_count += 1

    return {
        "status": "ok",
        "resource": "ap_lag",
        "data": data,
        "partial": bool(missing or invalid or unknown_count),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_count,
    }
