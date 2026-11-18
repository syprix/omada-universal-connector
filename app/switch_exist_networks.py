from __future__ import annotations

from collections import Counter
from typing import Any


class SwitchExistNetworksError(ValueError):
    pass


MAX_ROWS = 4096


def summarize_switch_exist_networks(rows: list[dict[str, Any]], support: dict[str, Any] | None = None) -> dict[str, object]:
    """Return VLAN and interface-type counts without network configuration data."""
    if len(rows) > MAX_ROWS:
        raise SwitchExistNetworksError("row_limit")
    by_vlan: Counter[int] = Counter()
    by_vlan_type: Counter[int] = Counter()
    primary = 0
    unknown_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            unknown_rows += 1
            continue
        vlan = row.get("vlan")
        vlan_type = row.get("vlanType")
        valid_vlan = isinstance(vlan, int) and not isinstance(vlan, bool) and 1 <= vlan <= 4090
        valid_type = isinstance(vlan_type, int) and not isinstance(vlan_type, bool) and vlan_type in {0, 1}
        if valid_vlan:
            by_vlan[vlan] += 1
        if valid_type:
            by_vlan_type[vlan_type] += 1
        if row.get("primary") is True:
            primary += 1
        invalid_primary = "primary" in row and not isinstance(row.get("primary"), bool)
        if not valid_vlan or not valid_type or invalid_primary:
            unknown_rows += 1
    flags: dict[str, bool | None] = {}
    allowed_flags = (
        "supportMultiVlan", "supportRA", "supportCustomDhcpOption",
        "supportDhcpNextServer", "supportArpDetection",
    )
    source = support if isinstance(support, dict) else {}
    for name in allowed_flags:
        value = source.get(name)
        flags[name] = value if isinstance(value, bool) else None
    return {
        "status": "ok",
        "resource": "switch_exist_networks",
        "count": len(rows),
        "summary": {
            "by_vlan": dict(sorted(by_vlan.items())),
            "by_vlan_type": dict(sorted(by_vlan_type.items())),
            "primary_count": primary,
            "unknown_rows": unknown_rows,
            "capabilities": flags,
        },
        "partial": unknown_rows > 0,
    }
