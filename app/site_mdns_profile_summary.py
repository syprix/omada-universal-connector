"""Redacted counts for configured Bonjour service profiles."""
from __future__ import annotations

from collections.abc import Mapping


MAX_PROFILES = 1_000
_PROFILE_FIELDS = frozenset({"id", "name", "serviceIds", "defaultProfile"})


def summarize_mdns_profiles(result: object) -> dict[str, object]:
    """Summarize profile flags and service-entry coverage without raw values."""
    if not isinstance(result, Mapping):
        return {"result_state": "invalid", "invalid_reason": "result_not_object",
                "profile_count": None, "partial": True, "truncated": False}
    if "data" not in result:
        return {"result_state": "missing", "missing_field": "data",
                "profile_count": None, "partial": True, "truncated": False}
    rows = result["data"]
    if not isinstance(rows, list):
        return {"result_state": "invalid", "invalid_reason": "data_not_array",
                "profile_count": None, "partial": True, "truncated": False}

    truncated = len(rows) > MAX_PROFILES
    bounded = rows[:MAX_PROFILES]
    defaults = {"true": 0, "false": 0, "unreported": 0, "invalid": 0}
    service_counts = {
        "zero": 0, "one": 0, "two": 0, "three": 0,
        "unreported": 0, "invalid": 0,
    }
    invalid_profile_rows = 0
    unknown_profile_field_count = 0
    for row in bounded:
        if not isinstance(row, Mapping):
            invalid_profile_rows += 1
            defaults["invalid"] += 1
            service_counts["invalid"] += 1
            continue

        unknown_profile_field_count += sum(1 for key in row if key not in _PROFILE_FIELDS)
        if "defaultProfile" not in row:
            defaults["unreported"] += 1
        elif type(row["defaultProfile"]) is bool:
            defaults["true" if row["defaultProfile"] else "false"] += 1
        else:
            defaults["invalid"] += 1

        if "serviceIds" not in row:
            service_counts["unreported"] += 1
            continue
        service_ids = row["serviceIds"]
        if (not isinstance(service_ids, list) or len(service_ids) > 3 or
                any(not isinstance(value, str) for value in service_ids)):
            service_counts["invalid"] += 1
            continue
        service_counts[{0: "zero", 1: "one", 2: "two", 3: "three"}[len(service_ids)]] += 1

    partial = bool(truncated or invalid_profile_rows or unknown_profile_field_count or
                   defaults["unreported"] or defaults["invalid"] or
                   service_counts["unreported"] or service_counts["invalid"])
    return {
        "result_state": "truncated" if truncated else "empty" if not bounded else "ok",
        "profile_count": len(bounded),
        "default_profile_flags": defaults,
        "service_entries_per_profile": service_counts,
        "invalid_profile_rows": invalid_profile_rows,
        "unknown_profile_field_count": unknown_profile_field_count,
        "truncated": truncated,
        "partial": partial,
    }
