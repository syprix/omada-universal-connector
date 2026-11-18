"""Redacted projection of documented per-band AP load-balancing settings."""
from __future__ import annotations


class ApLoadBalanceError(ValueError):
    """The AP load-balancing result cannot be bounded or projected safely."""

    def __init__(self, code: str = "ap_load_balance_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_BANDS = ("2g", "5g", "5g2", "6g")
_BOOL_SUFFIXES = ("maxClientsEnable", "rssiEnable")
_INT_SUFFIXES = ("maxClients", "threshold")
_FIELDS = tuple(f"{prefix}{band}" for band in _BANDS
                for prefix in (_BOOL_SUFFIXES[0], _INT_SUFFIXES[0],
                               _BOOL_SUFFIXES[1], _INT_SUFFIXES[1]))
_BOOL_FIELDS = frozenset(f"{prefix}{band}" for band in _BANDS for prefix in _BOOL_SUFFIXES)
_MAX_FIELDS = 32
_MAX_KEY_LENGTH = 128
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def _valid_value(field: str, value: object) -> bool:
    if field in _BOOL_FIELDS:
        return type(value) is bool
    if type(value) is not int or not _INT32_MIN <= value <= _INT32_MAX:
        return False
    if field.startswith("maxClients"):
        return 1 <= value <= 512
    return -95 <= value <= 0


def project_ap_load_balance(raw: object) -> dict[str, object]:
    """Return only the sixteen documented Boolean/int32 configuration fields.

    Range checks follow the supplied schema descriptions: maxClients is 1..512
    and threshold is -95..0. Unknown keys and all unrecognized values are
    dropped, with incompleteness reported through partial metadata. No extra
    band aliases or behavioral interpretation are introduced.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise ApLoadBalanceError()

    data: dict[str, bool | int] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for field in _FIELDS:
        if field not in raw:
            missing.append(field)
            continue
        value = raw[field]
        if _valid_value(field, value):
            data[field] = value
        else:
            invalid.append(field)

    unknown_field_count = 0
    for key in raw:
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise ApLoadBalanceError()
        if key not in _FIELDS:
            unknown_field_count += 1

    return {
        "status": "ok",
        "resource": "ap_load_balance",
        "data": data,
        "partial": bool(missing or invalid or unknown_field_count),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_field_count,
    }
