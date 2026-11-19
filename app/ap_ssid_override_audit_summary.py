"""Bounded, redacted summary of AP SSID override audit rows."""

from __future__ import annotations

from collections.abc import Mapping


class ApSsidOverrideAuditError(ValueError):
    """The controller response does not match its documented audit grid."""


_STRING_FIELDS = frozenset((
    "globalSsid", "oldSsidName", "newSsidName", "oldVlanId", "newVlanId",
))
_FLAG_FIELDS = {
    "passwordModified": "password_modified_count",
    "ssidNameModified": "ssid_name_modified_count",
    "vlanIdModified": "vlan_id_modified_count",
}
_ROW_FIELDS = _STRING_FIELDS | frozenset(_FLAG_FIELDS)


def summarize_ap_ssid_override_audit(
    result: object, *, page: int = 1, page_size: int = 100,
) -> dict[str, object]:
    """Return bounded change counts; discard SSID/VLAN values and all identities."""
    if not isinstance(result, Mapping) or len(result) > 12:
        raise ApSsidOverrideAuditError("result must be a bounded grid object")
    total = result.get("totalRows")
    current_page = result.get("currentPage")
    current_size = result.get("currentSize")
    rows = result.get("data")
    if (type(total) is not int or not 0 <= total <= 2**63 - 1 or
            type(current_page) is not int or current_page != page or
            type(current_size) is not int or not 0 <= current_size <= page_size or
            not isinstance(rows, list) or len(rows) > page_size or
            current_size != len(rows)):
        raise ApSsidOverrideAuditError("invalid audit grid metadata")

    counts = {value: 0 for value in _FLAG_FIELDS.values()}
    missing = invalid = unknown = invalid_rows = 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 32:
            invalid_rows += 1
            continue
        unknown += sum(key not in _ROW_FIELDS for key in row)
        for key in _STRING_FIELDS:
            if key in row and (not isinstance(row[key], str) or len(row[key]) > 512):
                invalid += 1
        for key, target in _FLAG_FIELDS.items():
            if key not in row:
                missing += 1
            elif not isinstance(row[key], bool):
                invalid += 1
            else:
                counts[target] += int(row[key])

    truncated = total > len(rows)
    return {
        "data": {
            "reported_total_row_count": total,
            "returned_row_count": len(rows),
            **counts,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "invalid_row_count": invalid_rows,
        "truncated": truncated,
        "partial": bool(missing or invalid or unknown or invalid_rows or truncated),
    }
