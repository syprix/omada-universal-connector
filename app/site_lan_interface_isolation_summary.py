"""Reported LAN interface isolation counts without identifiers."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_INTERFACES = 1_000


def summarize_lan_interface_isolation(rows: object) -> dict[str, Any]:
    if not isinstance(rows, list) or len(rows) > MAX_INTERFACES:
        raise ValueError("input_invalid")
    counts = {"isolated": 0, "not_isolated": 0, "unknown": 0, "missing": 0}
    invalid_rows = unknown_fields = 0
    for row in rows:
        if not isinstance(row, Mapping):
            invalid_rows += 1
            counts["unknown"] += 1
            continue
        unknown_fields += sum(field not in {"name", "id", "vlan", "vlans", "isolation"}
                              for field in row)
        value = row.get("isolation")
        if type(value) is bool:
            counts["isolated" if value else "not_isolated"] += 1
        elif "isolation" not in row:
            counts["missing"] += 1
        else:
            counts["unknown"] += 1
    partial = bool(counts["unknown"] or counts["missing"] or invalid_rows or unknown_fields)
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_lan_interface_isolation_summary",
        "reported_interface_count": len(rows),
        "reported_isolation": counts,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "interface_names_ids_and_vlan_values_returned": False,
        "network_separation_inferred": False,
    }
