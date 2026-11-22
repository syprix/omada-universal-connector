"""Redacted counts for documented policy-routing rows."""
from __future__ import annotations

from collections import Counter
from typing import Any


class SitePolicyRouteSummaryError(ValueError):
    pass


MAX_ROWS = 10_000
_SOURCE_DESTINATION_TYPES = {0: "network", 1: "ip_group", 2: "ip_port_group"}
_INTERFACE_TYPES = {0: "wan", 2: "l2tp", 3: "pptp", 4: "multi_select"}
_FIELDS = {
    "id", "index", "name", "status", "protocols", "interfaceType", "interfaceId",
    "wanPortIds", "vpnIds", "virtualWanIds", "backupInterface", "sourceType",
    "sourceIds", "destinationType", "destinationIds", "existVpnClient",
    "existVirtualWan", "existMulti", "existLocationGroupDest", "existDomainGroupDest",
    "existIpPortGroup",
}


def summarize_site_policy_routes(rows: list[Any]) -> dict[str, object]:
    if len(rows) > MAX_ROWS:
        raise SitePolicyRouteSummaryError("row_limit")
    source_types: Counter[str] = Counter()
    destination_types: Counter[str] = Counter()
    interface_types: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    references: Counter[str] = Counter()
    indices: list[int] = []
    invalid_rows = unknown_fields = invalid_fields = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            invalid_rows += 1
            continue
        unknown_fields += len(set(row) - _FIELDS)
        row_invalid = False
        for field, mapping, output in (
            ("sourceType", _SOURCE_DESTINATION_TYPES, source_types),
            ("destinationType", _SOURCE_DESTINATION_TYPES, destination_types),
            ("interfaceType", _INTERFACE_TYPES, interface_types),
        ):
            value = row.get(field)
            key = mapping.get(value) if isinstance(value, int) and not isinstance(value, bool) else None
            output[key or "unknown"] += 1
            if key is None:
                row_invalid = True
        status = row.get("status")
        statuses[str(status).lower() if isinstance(status, bool) else "unknown"] += 1
        if not isinstance(status, bool):
            row_invalid = True
        for field, label in (("sourceIds", "source"), ("destinationIds", "destination"),
                             ("wanPortIds", "wan"), ("vpnIds", "vpn"),
                             ("virtualWanIds", "virtual_wan")):
            value = row.get(field)
            if isinstance(value, list) and len(value) <= 1000:
                references[label] += len(value)
            elif field in row and value is not None:
                invalid_fields += 1
                row_invalid = True
        for field in ("interfaceId",):
            value = row.get(field)
            if isinstance(value, str) and value:
                references["interface"] += 1
            elif field in row and value is not None:
                invalid_fields += 1
                row_invalid = True
        index = row.get("index")
        if isinstance(index, int) and not isinstance(index, bool) and -(2**31) <= index < 2**31:
            indices.append(index)
        elif "index" in row and index is not None:
            invalid_fields += 1
            row_invalid = True
        if row_invalid:
            invalid_rows += 1
    unique_indices = len(indices) == len(set(indices))
    return {
        "status": "ok", "resource": "site_policy_route_summary", "count": len(rows),
        "summary": {
            "by_source_type": dict(sorted(source_types.items())),
            "by_destination_type": dict(sorted(destination_types.items())),
            "by_interface_type": dict(sorted(interface_types.items())),
            "by_enabled": dict(sorted(statuses.items())),
            "reference_occurrences": dict(sorted((k, v) for k, v in references.items() if v)),
            "index_count": len(indices), "indices_unique": unique_indices,
            "unknown_fields": unknown_fields, "invalid_fields": invalid_fields,
            "invalid_rows": invalid_rows,
        },
        "partial": bool(unknown_fields or invalid_fields or invalid_rows or not unique_indices),
        "ordering": "unique indices observed; precedence semantics are not documented in the exports",
        "protocols": "omitted; protocol value mapping is outside the three API exports",
    }
