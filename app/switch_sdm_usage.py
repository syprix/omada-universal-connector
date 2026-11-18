"""Typed projection of documented switch SDM category and entry-count values."""
from __future__ import annotations


class SwitchSdmUsageError(ValueError):
    """Response shape exceeds the documented, bounded projection."""


_CATEGORIES = {0, 1, 3, 4}
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def project_switch_sdm_usage(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or len(raw) > 16:
        raise SwitchSdmUsageError()
    if any(not isinstance(key, str) or len(key) > 128 for key in raw):
        raise SwitchSdmUsageError()
    data: dict[str, int] = {}
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0
    for field in ("category", "num"):
        if field not in raw:
            missing.append(field)
            omitted_count += 1
            continue
        value = raw[field]
        if (type(value) is int and _INT32_MIN <= value <= _INT32_MAX and
                (field != "category" or value in _CATEGORIES)):
            data[field] = value
        else:
            omitted.add(field)
            omitted_count += 1
    extras = sum(key not in {"category", "num"} for key in raw)
    if extras:
        omitted.add("unknown_fields")
        omitted_count += extras
    return {"status": "ok", "resource": "switch_sdm_usage", "data": data,
            "partial": bool(missing or omitted_count), "missing_fields": missing,
            "omitted_field_count": omitted_count,
            "omitted_fields": sorted(omitted)}
