"""Bounded, redacted summary of devices using one network VLAN."""
from __future__ import annotations


class VlanDeviceUsageError(ValueError):
    """Invalid or unsafe controller response."""


def project_site_vlan_device_usage_summary(raw: object) -> dict[str, object]:
    if not isinstance(raw, list) or len(raw) > 10_000:
        raise VlanDeviceUsageError("device_list_invalid")
    types = {"gateway": 0, "switch": 0, "ap": 0}
    dhcp_modes: dict[str, int] = {}
    stack_memberships = redacted = unknown = invalid = 0
    for row in raw:
        if not isinstance(row, dict):
            raise VlanDeviceUsageError("device_row_invalid")
        redacted += sum(key in row and row[key] is not None for key in ("name", "mac", "stackId"))
        unknown += sum(key not in {"name", "mac", "type", "stackId", "dhcpMode"} for key in row)
        if "type" in row and row["type"] is not None:
            value = row["type"]
            if type(value) is not int or value not in (1, 2, 3):
                invalid += 1
            else:
                types[{1: "gateway", 2: "switch", 3: "ap"}[value]] += 1
        if "stackId" in row and row["stackId"] is not None:
            value = row["stackId"]
            if not isinstance(value, str) or len(value) > 128 or any(ord(c) < 32 for c in value):
                invalid += 1
            elif value:
                stack_memberships += 1
        if "dhcpMode" in row and row["dhcpMode"] is not None:
            value = row["dhcpMode"]
            if type(value) is not int or not 0 <= value <= 2_147_483_647:
                invalid += 1
            else:
                key = str(value)
                dhcp_modes[key] = dhcp_modes.get(key, 0) + 1
    return {
        "device_count": len(raw),
        "device_type_counts": types,
        "stack_membership_count": stack_memberships,
        "dhcp_mode_counts": dhcp_modes,
        "partial": bool(unknown or invalid),
        "redacted_field_count": redacted,
        "unknown_field_count": unknown,
        "invalid_field_count": invalid,
    }
