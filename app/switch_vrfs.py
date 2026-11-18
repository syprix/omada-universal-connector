from __future__ import annotations

from collections import Counter
from typing import Any


class SwitchVrfsError(ValueError):
    pass


MAX_ROWS = 10_000
_RESOURCE_CODES = {0, 1, 2}


def summarize_switch_vrfs(rows: list[Any]) -> dict[str, object]:
    """Summarize VRF enablement and resource codes without names or IDs."""
    if len(rows) > MAX_ROWS:
        raise SwitchVrfsError("row_limit")
    by_ipv4: Counter[str] = Counter()
    by_ipv6: Counter[str] = Counter()
    by_resource: Counter[int] = Counter()
    defaults = 0
    unknown_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            unknown_rows += 1
            continue
        ipv4, ipv6, is_default, resource = (
            row.get("ipv4Enable"), row.get("ipv6Enable"),
            row.get("isDefault"), row.get("resource"))
        valid = (type(ipv4) is bool and type(ipv6) is bool and
                 type(is_default) is bool and type(resource) is int and
                 resource in _RESOURCE_CODES)
        if type(ipv4) is bool:
            by_ipv4[str(ipv4).lower()] += 1
        if type(ipv6) is bool:
            by_ipv6[str(ipv6).lower()] += 1
        if type(is_default) is bool and is_default:
            defaults += 1
        if type(resource) is int and resource in _RESOURCE_CODES:
            by_resource[resource] += 1
        if not valid:
            unknown_rows += 1
    return {
        "status": "ok",
        "resource": "switch_vrfs",
        "count": len(rows),
        "summary": {
            "by_ipv4_enabled": dict(sorted(by_ipv4.items())),
            "by_ipv6_enabled": dict(sorted(by_ipv6.items())),
            "default_count": defaults,
            "by_resource_code": dict(sorted(by_resource.items())),
            "unknown_rows": unknown_rows,
        },
        "partial": unknown_rows > 0,
    }
