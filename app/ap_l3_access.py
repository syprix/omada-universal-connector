"""Projection of AP layer-3 access support and enablement."""
from __future__ import annotations


class ApL3AccessError(ValueError):
    """The L3 access response is outside its projection contract."""


_FIELDS = frozenset({"enable", "supportL3Access"})


def summarize_ap_l3_access(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 8:
        raise ApL3AccessError()
    unknown = sum(1 for key in raw if key not in _FIELDS)
    missing = invalid = 0
    values: dict[str, bool] = {}
    for field in ("enable", "supportL3Access"):
        if field not in raw:
            missing += 1
        elif type(raw[field]) is bool:
            values[field] = raw[field]
        else:
            invalid += 1
    return {
        "status": "ok", "resource": "ap_l3_access",
        "enabled": values.get("enable"),
        "supported": values.get("supportL3Access"),
        "unknown_field_count": unknown, "invalid_field_count": invalid,
        "missing_field_count": missing,
        "partial": bool(unknown or invalid or missing),
    }
