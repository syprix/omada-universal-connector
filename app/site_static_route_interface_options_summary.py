"""Redacted summary of interfaces offered for static-route configuration."""
from __future__ import annotations

from collections.abc import Mapping


class StaticRouteInterfaceOptionsError(ValueError):
    pass


_INTERFACE_TYPES = {
    0: "wan",
    1: "lan",
    2: "l2tp",
    3: "pptp",
    5: "virtual_wan",
}
_ROW_FIELDS = frozenset(("interfaceType", "name", "id", "needNextHop"))


def summarize_static_route_interface_options(
        value: object, *, max_items: int = 1000) -> dict[str, object]:
    if (not isinstance(value, Mapping)
            or type(max_items) is not int or max_items < 1):
        raise StaticRouteInterfaceOptionsError("invalid result")
    rows = value.get("interfaceInfoList")
    if not isinstance(rows, list) or len(rows) > 10_000:
        raise StaticRouteInterfaceOptionsError("invalid interface list")
    selected_rows = rows[:max_items]

    interface_counts = {kind: 0 for kind in _INTERFACE_TYPES.values()}
    interface_counts["unknown"] = 0
    next_hop_counts = {"true": 0, "false": 0, "unknown": 0}
    invalid_record_count = invalid_field_count = unknown_field_count = 0
    unknown_interface_type_count = 0

    for row in selected_rows:
        if not isinstance(row, Mapping) or len(row) > 16:
            invalid_record_count += 1
            interface_counts["unknown"] += 1
            unknown_interface_type_count += 1
            next_hop_counts["unknown"] += 1
            continue

        unknown_field_count += sum(key not in _ROW_FIELDS for key in row)
        raw_type = row.get("interfaceType")
        if type(raw_type) is int and raw_type in _INTERFACE_TYPES:
            interface_counts[_INTERFACE_TYPES[raw_type]] += 1
        else:
            interface_counts["unknown"] += 1
            unknown_interface_type_count += 1
            if raw_type is not None:
                invalid_field_count += 1

        need_next_hop = row.get("needNextHop")
        if type(need_next_hop) is bool:
            next_hop_counts[str(need_next_hop).lower()] += 1
        else:
            next_hop_counts["unknown"] += 1
            if need_next_hop is not None:
                invalid_field_count += 1

    unknown_field_count += sum(key not in {"interfaceInfoList", "hasWanEnable"}
                               for key in value)
    has_wan = value.get("hasWanEnable")
    if has_wan is not None and type(has_wan) is not bool:
        invalid_field_count += 1
        has_wan = None

    return {
        "status": "ok",
        "resource": "site_static_route_interface_options_summary",
        "scope": "static_route_selection_options",
        "reported_interface_option_count": len(rows),
        "returned_interface_option_count": len(selected_rows),
        "interface_type_counts": interface_counts,
        "need_next_hop_value_counts": next_hop_counts,
        "has_wan_enabled": has_wan,
        "unknown_interface_type_count": unknown_interface_type_count,
        "invalid_record_count": invalid_record_count,
        "invalid_field_count": invalid_field_count,
        "unknown_field_count": unknown_field_count,
        "truncated": len(rows) > max_items,
        "partial": bool(invalid_record_count or invalid_field_count
                         or unknown_field_count or unknown_interface_type_count
                         or next_hop_counts["unknown"] or len(rows) > max_items),
    }
