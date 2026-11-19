from __future__ import annotations

from collections import Counter
from typing import Any


class SiteStaticRouteSummaryError(ValueError):
    pass


MAX_ROWS = 10_000


def summarize_site_static_routes(rows: list[Any]) -> dict[str, object]:
    """Count documented route metadata without returning route identifiers or values."""
    if len(rows) > MAX_ROWS:
        raise SiteStaticRouteSummaryError("row_limit")

    by_type: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    references: Counter[str] = Counter()
    unknown_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            unknown_rows += 1
            continue

        row_unknown = False
        route_type = row.get("routeType")
        valid_type = isinstance(route_type, int) and not isinstance(route_type, bool) and route_type in {0, 1}
        if valid_type:
            by_type["next_hop" if route_type == 0 else "interface"] += 1
        else:
            by_type["unknown"] += 1

        status = row.get("status")
        if isinstance(status, bool):
            by_status[str(status).lower()] += 1
        else:
            by_status["unknown"] += 1

        interface_id = row.get("interfaceId")
        if isinstance(interface_id, str) and interface_id:
            references["interface"] += 1
        elif "interfaceId" in row and interface_id is not None:
            row_unknown = True
        for key, label in (("existVpnClient", "vpn_client"), ("existVirtualWan", "virtual_wan")):
            value = row.get(key)
            if value is True:
                references[label] += 1
            elif key in row and not isinstance(value, bool):
                row_unknown = True

        if not valid_type or not isinstance(status, bool):
            row_unknown = True
        if row_unknown:
            unknown_rows += 1

    return {
        "status": "ok",
        "resource": "site_static_route_summary",
        "count": len(rows),
        "summary": {
            "by_type": dict(sorted(by_type.items())),
            "by_status": dict(sorted(by_status.items())),
            "reference_occurrences": dict(sorted(references.items())),
            "unknown_rows": unknown_rows,
        },
        "partial": unknown_rows > 0,
    }
