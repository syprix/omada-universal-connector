from __future__ import annotations

from collections import Counter
from typing import Any


class SwitchNetworksError(ValueError):
    pass


MAX_ROWS = 10000


def summarize_switch_networks(rows: list[dict[str, Any]]) -> dict[str, object]:
    """Summarize switch network rows without returning network or IP settings."""
    if len(rows) > MAX_ROWS:
        raise SwitchNetworksError("row_limit")
    by_vlan: Counter[int] = Counter()
    by_status: Counter[int] = Counter()
    by_dhcp_mode: Counter[int] = Counter()
    unknown_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            unknown_rows += 1
            continue
        vlan = row.get("vlan")
        status = row.get("status")
        mode = row.get("mode")
        valid_vlan = isinstance(vlan, int) and not isinstance(vlan, bool) and -(2**31) <= vlan <= 2**31 - 1
        valid_status = isinstance(status, int) and not isinstance(status, bool) and status in {0, 1}
        valid_mode = isinstance(mode, int) and not isinstance(mode, bool) and mode in {0, 1, 2}
        if valid_vlan:
            by_vlan[vlan] += 1
        if valid_status:
            by_status[status] += 1
        if valid_mode:
            by_dhcp_mode[mode] += 1
        if not (valid_vlan and valid_status and valid_mode):
            unknown_rows += 1
    return {
        "status": "ok",
        "resource": "switch_networks",
        "count": len(rows),
        "summary": {
            "by_vlan": dict(sorted(by_vlan.items())),
            "by_status_code": dict(sorted(by_status.items())),
            "by_dhcp_mode_code": dict(sorted(by_dhcp_mode.items())),
            "unknown_rows": unknown_rows,
        },
        "partial": unknown_rows > 0,
    }
