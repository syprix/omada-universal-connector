"""Redacted projection of documented AP LAN traffic counters."""
from __future__ import annotations


class ApLanTrafficError(ValueError):
    """The LAN-traffic result cannot be bounded or projected safely."""

    def __init__(self, code: str = "ap_lan_traffic_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_FIELDS = (
    "rxPkts", "txPkts", "rx", "tx", "rxDropPkts", "txDropPkts",
    "rxErrPkts", "txErrPkts",
)
_MAX_FIELDS = 32
_MAX_KEY_LENGTH = 128
_INT64_MAX = 2**63 - 1


def project_ap_lan_traffic(raw: object) -> dict[str, object]:
    """Project optional nonnegative int64 traffic counters without inference.

    The schema describes ``rx`` and ``tx`` as byte totals and the remaining
    values as packet counters. No rate, interval, reset, or health meaning is
    inferred. Missing, invalid, and unknown fields mark the output partial.
    """
    if raw is None:
        return {
            "status": "ok", "resource": "ap_lan_traffic", "data": {},
            "partial": True, "missing_fields": list(_FIELDS),
            "invalid_fields": [], "unknown_field_count": 0,
        }
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise ApLanTrafficError()

    for key in raw:
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise ApLanTrafficError()

    data: dict[str, int] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for field in _FIELDS:
        if field not in raw:
            missing.append(field)
            continue
        value = raw[field]
        if type(value) is int and 0 <= value <= _INT64_MAX:
            data[field] = value
        else:
            invalid.append(field)

    unknown_count = sum(1 for key in raw if key not in _FIELDS)
    return {
        "status": "ok",
        "resource": "ap_lan_traffic",
        "data": data,
        "partial": bool(missing or invalid or unknown_count),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_count,
    }
