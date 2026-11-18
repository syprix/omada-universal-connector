from __future__ import annotations

from typing import Any


class SwitchVlanInterfacesError(ValueError):
    pass


MAX_ROWS = 4096
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1


def summarize_switch_vlan_interfaces(rows: list[Any]) -> dict[str, object]:
    """Count VLAN interfaces without returning their names or identifiers."""
    if len(rows) > MAX_ROWS:
        raise SwitchVlanInterfacesError("row_limit")
    vlan_ids: set[int] = set()
    unknown_rows = 0
    for row in rows:
        vlan_id = row.get("vlanId") if isinstance(row, dict) else None
        if (type(vlan_id) is int and _INT32_MIN <= vlan_id <= _INT32_MAX):
            vlan_ids.add(vlan_id)
        else:
            unknown_rows += 1
    return {
        "status": "ok",
        "resource": "switch_vlan_interfaces",
        "count": len(rows),
        "summary": {
            "unique_vlan_count": len(vlan_ids),
            "unknown_rows": unknown_rows,
        },
        "partial": unknown_rows > 0,
    }
