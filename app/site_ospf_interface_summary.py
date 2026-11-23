"""Redacted OSPF interface configuration counts."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_ROWS = 1_000
OPTIONAL_FIELDS = (
    "type", "isStack", "passiveEnable", "deadInterval", "loopbackId",
    "loopbackInterfaceId", "stackId",
)


def summarize_ospf_interfaces(
        rows: object, total_rows: object, omitted_rows: int) -> dict[str, Any]:
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or
            type(total_rows) is not int or total_rows < len(rows) or
            type(omitted_rows) is not int or omitted_rows < 0 or
            omitted_rows > total_rows - len(rows)):
        raise ValueError("input_invalid")
    interface_type = {"vlan": 0, "loopback": 0, "unknown": 0, "missing": 0}
    network_type = {"broadcast": 0, "non_broadcast": 0,
                    "point_to_multipoint": 0, "point_to_point": 0,
                    "unknown": 0, "missing": 0}
    cost = {"valid": 0, "invalid": 0, "missing": 0}
    option_coverage = {field: {"present": 0, "missing": 0, "invalid": 0}
                       for field in OPTIONAL_FIELDS}
    invalid_rows = unknown_fields = 0
    accepted = {"id", "deviceName", "isStack", "mac", "type", "stackId",
                "vlanInterfaceId", "vlanInterfaceName", "vlanId", "loopbackInterfaceId",
                "loopbackId", "cost", "networkType", "passiveEnable", "helloInterval",
                "deadInterval", "authenticationType", "simpleKey", "md5KeyId", "md5Key"}
    partial = omitted_rows > 0
    for row in rows:
        if not isinstance(row, Mapping):
            invalid_rows += 1
            interface_type["unknown"] += 1
            network_type["unknown"] += 1
            cost["invalid"] += 1
            for counts in option_coverage.values():
                counts["invalid"] += 1
            partial = True
            continue
        unknown_fields += sum(field not in accepted for field in row)
        kind = row.get("type")
        if type(kind) is int and kind in (0, 1):
            interface_type["vlan" if kind == 0 else "loopback"] += 1
        elif "type" not in row:
            interface_type["missing"] += 1
        else:
            interface_type["unknown"] += 1
        ntype = row.get("networkType")
        if type(ntype) is int and 0 <= ntype <= 3:
            network_type[("broadcast", "non_broadcast", "point_to_multipoint",
                          "point_to_point")[ntype]] += 1
        elif "networkType" not in row:
            network_type["missing"] += 1
        else:
            network_type["unknown"] += 1
        value = row.get("cost")
        if type(value) is int and 1 <= value <= 65_535:
            cost["valid"] += 1
        elif "cost" not in row:
            cost["missing"] += 1
        else:
            cost["invalid"] += 1
        for field, counts in option_coverage.items():
            if field not in row:
                counts["missing"] += 1
            elif field in ("isStack", "passiveEnable") and type(row[field]) is not bool:
                counts["invalid"] += 1
            elif field in ("type", "loopbackId") and type(row[field]) is not int:
                counts["invalid"] += 1
            elif field in ("deadInterval",) and (type(row[field]) is not int or
                                                   not 1 <= row[field] <= 65_535):
                counts["invalid"] += 1
            elif field in ("loopbackInterfaceId", "stackId") and type(row[field]) is not str:
                counts["invalid"] += 1
            else:
                counts["present"] += 1
    partial = partial or bool(invalid_rows or unknown_fields or interface_type["unknown"] or
                              interface_type["missing"] or network_type["unknown"] or
                              network_type["missing"] or cost["invalid"] or cost["missing"] or
                              any(x["invalid"] for x in option_coverage.values()))
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_ospf_interface_summary",
        "reported_interface_total": total_rows,
        "returned_interface_count": len(rows),
        "omitted_interface_count": omitted_rows,
        "by_documented_interface_type": interface_type,
        "by_documented_network_type": network_type,
        "reported_link_cost_range": {"documented_minimum": 1, "documented_maximum": 65_535,
                                      **cost},
        "reported_optional_field_coverage": option_coverage,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "interface_names_ids_macs_vlan_values_and_authentication_keys_returned": False,
        "ospf_neighbor_state_inferred": False,
    }
