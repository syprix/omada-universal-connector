"""Redacted summary for the documented AP-group inventory read."""
from __future__ import annotations

from typing import Any


class ApGroupSummaryError(ValueError):
    """The controller AP-group result is outside the bounded source schema."""


_ROW_FIELDS = frozenset({"id", "name", "primary", "apNum", "remainingBinding", "ssidNameList"})
_GRID_FIELDS = frozenset({
    "totalRows", "currentPage", "currentSize", "data", "maxSsids2G", "maxSsids5G",
    "maxSsids6G", "maxSsidsMlo",
})
_MAX_GROUPS = 10_000
_MAX_BINDINGS_PER_GROUP = 8
_INT32_MAX = 2**31 - 1
_INT64_MAX = 2**63 - 1
_BANDS = (("0", "2g"), ("1", "5g"), ("2", "6g"))
_MAX_FIELDS = {
    "maxSsids2G": "2g",
    "maxSsids5G": "5g",
    "maxSsids6G": "6g",
    "maxSsidsMlo": "mlo",
}


def _nonnegative_int(value: object, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def project_site_ap_group_summary(raw: object) -> dict[str, Any]:
    """Summarize AP groups while dropping group IDs, names, and SSID labels."""
    if not isinstance(raw, dict) or len(raw) > 16:
        raise ApGroupSummaryError("response_invalid")
    total = raw.get("totalRows")
    rows = raw.get("data")
    if (not _nonnegative_int(total, _INT64_MAX) or not isinstance(rows, list) or
            len(rows) > _MAX_GROUPS or len(rows) != total):
        raise ApGroupSummaryError("response_invalid")

    primary = non_primary = primary_unknown = 0
    ap_total = ap_known = 0
    ssid_list_groups = 0
    redacted = 0
    unknown = sum(1 for field in raw if field not in _GRID_FIELDS)
    invalid = 0
    remaining = {band: {"count": 0, "known_groups": 0} for _, band in _BANDS}
    max_ssids: dict[str, int] = {}

    for field, band in _MAX_FIELDS.items():
        if field in raw:
            value = raw[field]
            if _nonnegative_int(value, _INT32_MAX):
                max_ssids[band] = value
            else:
                invalid += 1

    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            raise ApGroupSummaryError("response_invalid")
        unknown += sum(1 for key in row if key not in _ROW_FIELDS)
        for field in ("id", "name"):
            if field in row:
                redacted += 1

        if "primary" not in row:
            primary_unknown += 1
        elif type(row["primary"]) is bool:
            if row["primary"]:
                primary += 1
            else:
                non_primary += 1
        else:
            invalid += 1
            primary_unknown += 1

        if "apNum" not in row:
            pass
        elif _nonnegative_int(row["apNum"], _INT64_MAX):
            ap_total += row["apNum"]
            ap_known += 1
        else:
            invalid += 1

        if "ssidNameList" in row:
            values = row["ssidNameList"]
            if isinstance(values, list) and all(isinstance(value, str) for value in values):
                ssid_list_groups += 1
                redacted += len(values)
            else:
                invalid += 1

        if "remainingBinding" in row:
            bindings = row["remainingBinding"]
            if not isinstance(bindings, dict) or len(bindings) > _MAX_BINDINGS_PER_GROUP:
                invalid += 1
            else:
                known_keys = {key for key, _ in _BANDS}
                unknown += len(set(bindings) - known_keys)
                for key, band in _BANDS:
                    if key not in bindings:
                        continue
                    value = bindings[key]
                    if _nonnegative_int(value, _INT32_MAX):
                        remaining[band]["count"] += value
                        remaining[band]["known_groups"] += 1
                    else:
                        invalid += 1

    group_count = len(rows)
    for band in remaining:
        remaining[band]["unknown_groups"] = group_count - remaining[band]["known_groups"]
    partial = bool(unknown or invalid or primary_unknown or ap_known != group_count or
                   ssid_list_groups != group_count or any(
                       remaining[band]["unknown_groups"] for band in remaining) or
                   set(max_ssids) != set(_MAX_FIELDS.values()))
    return {
        "status": "ok",
        "resource": "site_ap_group_summary",
        "total_groups": total,
        "primary_groups": primary,
        "non_primary_groups": non_primary,
        "primary_state_unknown_groups": primary_unknown,
        "ap_count_total": ap_total if ap_known == group_count else None,
        "ap_count_known_groups": ap_known,
        "groups_with_ssid_list": ssid_list_groups,
        "remaining_ssid_bindings": remaining,
        "max_ssids_by_band": max_ssids,
        "partial": partial,
        "redacted_field_count": redacted,
        "unknown_field_count": unknown,
        "invalid_field_count": invalid,
    }
