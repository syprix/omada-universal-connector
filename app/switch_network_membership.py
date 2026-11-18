"""Bounded network-to-port membership counts for one switch."""
from __future__ import annotations


class SwitchNetworkMembershipError(ValueError):
    """Input exceeds the documented membership projection contract."""


_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAX_ROWS = 10_000
_MAX_MEMBERS = 100_000
_GROUPS = {
    "native": ("nativePorts", "nativeStPorts", "nativeLags"),
    "tagged": ("tagPorts", "tagStPorts", "tagLags"),
    "untagged": ("untagPorts", "untagStPorts", "untagLags"),
}


def summarize_switch_network_membership(rows: object) -> dict[str, object]:
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise SwitchNetworkMembershipError()
    counts = {group: {"ports": 0, "lags": 0} for group in _GROUPS}
    isolated_networks = 0
    unknown_network_rows = 0
    incomplete_membership_rows = 0
    member_total = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 8:
            unknown_network_rows += 1
            continue
        isolation = row.get("isolation")
        if type(isolation) is bool:
            isolated_networks += int(isolation)
        else:
            unknown_network_rows += 1
        info = row.get("portLagNetworkInfo")
        if not isinstance(info, dict) or len(info) > 16:
            incomplete_membership_rows += 1
            continue
        row_incomplete = False
        for group, fields in _GROUPS.items():
            for field in fields:
                values = info.get(field)
                if not isinstance(values, list):
                    row_incomplete = True
                    continue
                member_total += len(values)
                if member_total > _MAX_MEMBERS:
                    raise SwitchNetworkMembershipError()
                kind = "lags" if field.endswith("Lags") else "ports"
                for value in values:
                    if field.endswith("StPorts"):
                        valid = isinstance(value, str) and 0 < len(value) <= 32
                    else:
                        valid = type(value) is int and _INT32_MIN <= value <= _INT32_MAX
                    if valid:
                        counts[group][kind] += 1
                    else:
                        row_incomplete = True
        if row_incomplete:
            incomplete_membership_rows += 1
    partial = unknown_network_rows > 0 or incomplete_membership_rows > 0
    return {
        "status": "ok",
        "resource": "switch_network_membership",
        "count": len(rows),
        "summary": {
            "isolated_networks": isolated_networks,
            "memberships": counts,
            "unknown_network_rows": unknown_network_rows,
            "incomplete_membership_rows": incomplete_membership_rows,
        },
        "partial": partial,
    }
