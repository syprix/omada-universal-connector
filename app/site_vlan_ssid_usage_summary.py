"""Bounded, redacted summary of SSIDs using one network VLAN."""
from __future__ import annotations


class VlanSsidUsageError(ValueError):
    """Invalid or unsafe controller response."""


def project_site_vlan_ssid_usage_summary(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise VlanSsidUsageError("grid_invalid")
    total, rows = raw.get("totalRows"), raw.get("data")
    if (type(total) is not int or total < 0 or total > 10_000 or
            not isinstance(rows, list) or len(rows) != total):
        raise VlanSsidUsageError("grid_invalid")
    wlan_groups: set[str] = set()
    unknown = invalid = redacted = 0
    for row in rows:
        if not isinstance(row, dict):
            raise VlanSsidUsageError("row_invalid")
        if "id" in row or "name" in row or "wlanName" in row:
            redacted += sum(key in row for key in ("id", "name", "wlanName"))
        unknown += sum(key not in {"id", "name", "wlanId", "wlanName"} for key in row)
        if "wlanId" not in row:
            unknown += 1
            continue
        value = row["wlanId"]
        if value is None:
            unknown += 1
            continue
        if not isinstance(value, str) or not value or len(value) > 128 or any(ord(c) < 32 for c in value):
            invalid += 1
            continue
        wlan_groups.add(value)
    return {
        "ssid_count": total,
        "wlan_group_count": len(wlan_groups),
        "partial": bool(unknown or invalid),
        "redacted_field_count": redacted,
        "unknown_field_count": unknown,
        "invalid_field_count": invalid,
    }
