from __future__ import annotations

from collections import Counter
from typing import Any


class SwitchStaticRoutesError(ValueError):
    pass


MAX_ROWS = 10000


def summarize_switch_static_routes(rows: list[Any], support_ipv6: object = None) -> dict[str, object]:
    """Summarize static-route metadata without returning destinations or next hops."""
    if len(rows) > MAX_ROWS:
        raise SwitchStaticRoutesError("row_limit")
    by_status: Counter[str] = Counter()
    by_ip_version: Counter[int] = Counter()
    by_distance: Counter[int] = Counter()
    by_resource: Counter[int] = Counter()
    destinations: Counter[int] = Counter()
    unknown_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            unknown_rows += 1
            continue
        status, distance, dsts = row.get("status"), row.get("distance"), row.get("destinations")
        ip_version, resource = row.get("ipVersion"), row.get("resource")
        valid_status = isinstance(status, bool)
        valid_distance = isinstance(distance, int) and not isinstance(distance, bool) and 1 <= distance <= 255
        valid_destinations = (isinstance(dsts, list) and len(dsts) <= 16 and
                              all(isinstance(destination, str) for destination in dsts))
        if valid_status:
            by_status[str(status).lower()] += 1
        if valid_distance:
            by_distance[distance] += 1
        if valid_destinations:
            destinations[len(dsts)] += 1
        valid_ip_version = ip_version is None or (
            isinstance(ip_version, int) and not isinstance(ip_version, bool) and ip_version in {0, 1})
        if ip_version is not None and valid_ip_version:
            by_ip_version[ip_version] += 1
        valid_resource = resource is None or (
            isinstance(resource, int) and not isinstance(resource, bool) and resource in {0, 1, 2})
        if resource is not None and valid_resource:
            by_resource[resource] += 1
        if not (valid_status and valid_distance and valid_destinations and valid_ip_version and valid_resource):
            unknown_rows += 1
    support = support_ipv6 if isinstance(support_ipv6, bool) else None
    return {
        "status": "ok",
        "resource": "switch_static_routes",
        "count": len(rows),
        "summary": {
            "by_status": dict(sorted(by_status.items())),
            "by_ip_version": dict(sorted(by_ip_version.items())),
            "by_distance": dict(sorted(by_distance.items())),
            "by_resource_code": dict(sorted(by_resource.items())),
            "by_destination_count": dict(sorted(destinations.items())),
            "support_ipv6_static_routing": support,
            "unknown_rows": unknown_rows,
        },
        "partial": unknown_rows > 0,
    }
