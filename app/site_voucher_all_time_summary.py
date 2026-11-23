"""Conservative projection of all-time hotspot voucher summary fields."""
from __future__ import annotations

from collections.abc import Mapping


class VoucherSummaryError(ValueError):
    pass


_CATEGORIES = ("current", "inuse", "expired", "unused", "created")
_FIELDS = {"count", "amount", "duration", "currency"}
_INT64_MAX = 2**63 - 1
_MISSING = object()


def _state(value: object, expected: type) -> str:
    if value is _MISSING:
        return "missing"
    if expected is int:
        valid = type(value) is int and 0 <= value <= _INT64_MAX
    else:
        valid = isinstance(value, expected) and len(value) <= (256 if expected is str else 0)
    return "present" if valid else "invalid"


def summarize_all_time_vouchers(raw: object) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise VoucherSummaryError("summary_invalid")
    unknown_top = [key for key in raw if key not in {*_CATEGORIES, "supportVoucherTrafficStat"}]
    if any(not isinstance(key, str) or len(key) > 128 for key in raw):
        raise VoucherSummaryError("summary_invalid")
    missing: list[str] = []
    invalid: list[str] = []
    unknown_count = len(unknown_top)
    counts: dict[str, int | None] = {}
    durations: dict[str, int | None] = {}
    for category in _CATEGORIES:
        if category not in raw:
            item = {}
        else:
            item = raw[category]
        if not isinstance(item, Mapping):
            invalid.append(category)
            item = {}
        unknown = set(item) - _FIELDS
        unknown_count += len(unknown)
        for source, output, expected in (
                ("count", "count", int), ("duration", "duration_minutes", int)):
            state = _state(item.get(source, _MISSING), expected)
            value = item.get(source) if state == "present" else None
            (counts if output == "count" else durations)[category] = value
            if state == "missing":
                missing.append(f"{category}.{source}")
            elif state == "invalid":
                invalid.append(f"{category}.{source}")

    support = raw.get("supportVoucherTrafficStat", _MISSING)
    if support is _MISSING:
        missing.append("supportVoucherTrafficStat")
        support_value = None
    elif type(support) is bool:
        support_value = support
    else:
        invalid.append("supportVoucherTrafficStat")
        support_value = None
    summary: dict[str, object] = {
        "voucher_counts": counts,
        "voucher_durations_minutes": durations,
        "voucher_traffic_statistics_supported": support_value,
        "missing_fields": missing,
        "invalid_fields": invalid,
        "partial": bool(missing or invalid or unknown_count),
    }
    if unknown_count:
        summary["unknown_field_count"] = unknown_count
    return summary
