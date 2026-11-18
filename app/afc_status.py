"""Strict, redacted projection of the documented AP AFC status response."""
from __future__ import annotations


class AfcStatusError(ValueError):
    """A response cannot be projected safely; carries only a fixed code."""

    def __init__(self, code: str = "afc_status_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 32
_INT32_MIN, _INT32_MAX = -(2**31), 2**31 - 1
_INT64_MIN, _INT64_MAX = -(2**63), 2**63 - 1
_BOOL_FIELDS = ("status", "lastResponse", "processing", "available6g")
_INT32_FIELDS = ("errCode", "errMain", "errDetail")
_INT64_FIELDS = ("expirationTimeSec", "lastResponseTimeSec")
_FIELDS = frozenset((*_BOOL_FIELDS, *_INT32_FIELDS, *_INT64_FIELDS))


def project_afc_status(raw: object) -> dict[str, object]:
    """Keep only the nine documented AFC status values.

    Timestamp integers are retained unchanged in the documented seconds
    fields; error codes remain numeric and are not interpreted. Unknown and
    malformed fields are omitted and reported only through safe metadata.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise AfcStatusError()

    data: dict[str, bool | int] = {}
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0

    for field in _FIELDS:
        if field not in raw:
            missing.append(field)
            omitted_count += 1
            continue
        value = raw[field]
        if field in _BOOL_FIELDS:
            valid = type(value) is bool
        elif field in _INT32_FIELDS:
            valid = type(value) is int and _INT32_MIN <= value <= _INT32_MAX
        else:
            valid = type(value) is int and _INT64_MIN <= value <= _INT64_MAX
        if valid:
            data[field] = value
        else:
            omitted.add(field)
            omitted_count += 1

    unknown_count = sum(1 for field in raw if field not in _FIELDS)
    if unknown_count:
        omitted.add("unknown_fields")
        omitted_count += unknown_count

    return {
        "status": "ok",
        "resource": "ap_afc_status",
        "data": data,
        "partial": bool(missing or omitted_count),
        "missing_fields": sorted(missing),
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
    }
