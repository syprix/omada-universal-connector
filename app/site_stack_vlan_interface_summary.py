"""Redacted counts for documented VLAN interfaces on one switch stack."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_ROWS = 1_000


def summarize_stack_vlan_interfaces(rows: object) -> dict[str, Any]:
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("input_invalid")

    ids = {"unique": 0, "duplicate": 0, "missing": 0, "invalid": 0}
    names = {"present": 0, "missing": 0, "invalid": 0}
    vlan_ids = {"present": 0, "missing": 0, "invalid": 0}
    seen: set[str] = set()
    invalid_rows = unknown_fields = 0
    allowed_fields = {"vlanInterfaceId", "vlanInterfaceName", "vlanId"}

    for row in rows:
        if not isinstance(row, Mapping):
            invalid_rows += 1
            ids["invalid"] += 1
            names["invalid"] += 1
            vlan_ids["invalid"] += 1
            continue

        unknown_fields += sum(key not in allowed_fields for key in row)

        interface_id = row.get("vlanInterfaceId")
        if "vlanInterfaceId" not in row or interface_id is None:
            ids["missing"] += 1
        elif not isinstance(interface_id, str) or not interface_id.strip():
            ids["invalid"] += 1
        elif interface_id in seen:
            ids["duplicate"] += 1
        else:
            seen.add(interface_id)
            ids["unique"] += 1

        name = row.get("vlanInterfaceName")
        if "vlanInterfaceName" not in row or name is None:
            names["missing"] += 1
        elif isinstance(name, str) and name:
            names["present"] += 1
        else:
            names["invalid"] += 1

        vlan_id = row.get("vlanId")
        if "vlanId" not in row or vlan_id is None:
            vlan_ids["missing"] += 1
        elif type(vlan_id) is int:
            vlan_ids["present"] += 1
        else:
            vlan_ids["invalid"] += 1

    partial = bool(invalid_rows or unknown_fields or ids["duplicate"] or
                   ids["missing"] or ids["invalid"] or names["missing"] or
                   names["invalid"] or vlan_ids["missing"] or vlan_ids["invalid"])
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_stack_vlan_interface_summary",
        "reported_interface_count": len(rows),
        "interface_id_coverage": ids,
        "interface_name_coverage": names,
        "vlan_id_coverage": vlan_ids,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "interface_names_ids_and_vlan_numbers_returned": False,
    }
