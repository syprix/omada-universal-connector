"""Redacted VLAN-count summary for a switch's port and LAG networks."""
from __future__ import annotations


class SwitchPortNetworksError(ValueError):
    """Input exceeds the bounded network summary contract."""


_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAX_ROWS = 10_000


def summarize_switch_port_networks(rows: object) -> dict[str, object]:
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise SwitchPortNetworksError()
    by_vlan: dict[int, int] = {}
    unknown_vlan_rows = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 16:
            unknown_vlan_rows += 1
            continue
        vlan = row.get("vlan")
        if type(vlan) is not int or not _INT32_MIN <= vlan <= _INT32_MAX:
            unknown_vlan_rows += 1
            continue
        by_vlan[vlan] = by_vlan.get(vlan, 0) + 1
    vlans = [{"vlan_id": vlan, "network_count": by_vlan[vlan]}
             for vlan in sorted(by_vlan)]
    return {"status": "ok", "resource": "switch_port_networks", "count": len(rows),
            "summary": {"vlans": vlans, "unknown_vlan_rows": unknown_vlan_rows},
            "partial": unknown_vlan_rows > 0}
