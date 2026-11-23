"""Redacted summary of documented topology root-candidate nodes."""
from __future__ import annotations

from collections.abc import Mapping


class TopologyRootCandidatesError(ValueError):
    pass


_FIELDS = frozenset(("type", "specificType", "name", "nameList", "mac",
                     "macList", "model", "modelVersion", "showModel",
                     "isRoot", "stackGroup", "clientType", "omadaDeviceType"))


def summarize_topology_root_candidates(value: object, *, max_items: int = 1000
                                       ) -> dict[str, object]:
    if not isinstance(value, list) or type(max_items) is not int or max_items < 1:
        raise TopologyRootCandidatesError("invalid root candidate list")
    types = {"switch": 0, "olt": 0, "other": 0, "unknown": 0}
    specific = {"mlag": 0, "vrrp": 0, "unknown": 0, "unreported": 0}
    roots = {"yes": 0, "no": 0, "unreported": 0}
    stacks = {"yes": 0, "no": 0, "unreported": 0}
    detail_fields = {"client_type_reported": 0, "client_type_unreported": 0,
                     "omada_device_type_reported": 0,
                     "omada_device_type_unreported": 0}
    invalid = unknown = invalid_fields = 0
    for row in value[:max_items]:
        if not isinstance(row, Mapping) or len(row) > 32:
            invalid += 1
            types["unknown"] += 1
            continue
        unknown += sum(key not in _FIELDS for key in row)
        kind = row.get("type")
        types[kind if isinstance(kind, str) and kind in ("switch", "olt", "other") else "unknown"] += 1
        code = row.get("specificType")
        if code is None:
            specific["unreported"] += 1
        elif type(code) is int and code in (0, 1):
            specific["mlag" if code == 0 else "vrrp"] += 1
        else:
            specific["unknown"] += 1
            invalid_fields += 1
        for field, output in (("isRoot", roots), ("stackGroup", stacks)):
            flag = row.get(field)
            if flag is None:
                output["unreported"] += 1
            elif type(flag) is bool:
                output["yes" if flag else "no"] += 1
            else:
                output["unreported"] += 1
                invalid_fields += 1
        for field, reported, unreported in (
                ("clientType", "client_type_reported", "client_type_unreported"),
                ("omadaDeviceType", "omada_device_type_reported",
                 "omada_device_type_unreported")):
            detail = row.get(field)
            if detail is None:
                detail_fields[unreported] += 1
            elif isinstance(detail, str):
                detail_fields[reported] += 1
            else:
                detail_fields[unreported] += 1
                invalid_fields += 1
    truncated = len(value) > max_items
    return {
        "status": "ok", "resource": "site_topology_root_candidates_summary",
        "root_candidate_count": len(value), "returned_count": min(len(value), max_items),
        "node_type_counts": types, "specific_type_counts": specific,
        "root_flag_counts": roots, "stack_group_flag_counts": stacks,
        "specific_detail_field_counts": detail_fields,
        "invalid_record_count": invalid, "invalid_field_count": invalid_fields,
        "unknown_field_count": unknown, "truncated": truncated,
        "partial": bool(invalid or invalid_fields or unknown or truncated or types["unknown"]),
    }
