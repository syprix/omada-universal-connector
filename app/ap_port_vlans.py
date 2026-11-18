"""Compact, redacted projection of an AP's documented port VLAN rows."""
from __future__ import annotations


class ApPortVlansError(ValueError):
    """The VLAN grid cannot be projected within its documented bounds."""


_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAX_ROWS = 10_000
_ROW_FIELDS = frozenset({"localVlanId", "localVlanNetworkId", "name", "ipaddr",
                         "nativePort", "tagPort", "untagPort"})
_PORT_FIELDS = ("nativePort", "tagPort", "untagPort")


def summarize_ap_port_vlans(grid: object) -> dict[str, object]:
    if not isinstance(grid, dict) or len(grid) > 8:
        raise ApPortVlansError()
    rows = grid.get("data")
    total = grid.get("totalRows")
    page = grid.get("currentPage")
    size = grid.get("currentSize")
    if (not isinstance(rows, list) or len(rows) > _MAX_ROWS or
            type(total) is not int or not 0 <= total <= _MAX_ROWS or
            type(page) is not int or page < 1 or
            type(size) is not int or size < 0 or size > _MAX_ROWS):
        raise ApPortVlansError()
    vlan_ids: dict[int, int] = {}
    port_counts = {field: 0 for field in _PORT_FIELDS}
    invalid = unknown = redacted = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            invalid += 1
            continue
        unknown += sum(1 for key in row if key not in _ROW_FIELDS)
        value = row.get("localVlanId")
        if type(value) is int and _INT32_MIN <= value <= _INT32_MAX:
            vlan_ids[value] = vlan_ids.get(value, 0) + 1
        elif "localVlanId" in row:
            invalid += 1
        for field in _PORT_FIELDS:
            if field not in row:
                continue
            value = row[field]
            if not isinstance(value, list) or len(value) > 128 or any(
                    not isinstance(item, str) or len(item) > 64 for item in value):
                invalid += 1
            else:
                port_counts[field] += len(value)
        redacted += sum(1 for field in ("localVlanNetworkId", "name", "ipaddr")
                        if field in row)
    return {
        "status": "ok", "resource": "ap_port_vlans",
        "count": len(rows), "total_rows": total,
        "vlan_id_counts": dict(sorted(vlan_ids.items())),
        "port_counts": port_counts,
        "redacted_field_count": redacted,
        "unknown_field_count": unknown, "invalid_row_or_field_count": invalid,
        "partial": bool(unknown or invalid or len(rows) != total),
    }
