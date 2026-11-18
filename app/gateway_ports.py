"""Redacted projection of documented gateway port inventory."""
from __future__ import annotations

from typing import Any


class GatewayPortsError(ValueError):
    """The gateway port result cannot be safely bounded."""


_FIELDS = frozenset({"port", "type", "physicalType", "mode", "name"})
_CODES = frozenset({"type", "physicalType", "mode"})


def project_gateway_ports(raw: object) -> dict[str, Any]:
    # Hardware Controller 6.3 returns the port rows directly; ER7212PC wraps
    # them in the documented ``osgPortInfos`` object.
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and len(raw) <= 16:
        rows = raw.get("osgPortInfos")
    else:
        raise GatewayPortsError("response_invalid")
    if not isinstance(rows, list) or len(rows) > 64:
        raise GatewayPortsError("response_invalid")
    items: list[dict[str, int]] = []
    partial = False
    unknown = redacted = omitted = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            raise GatewayPortsError("response_invalid")
        item: dict[str, int] = {}
        for field, value in row.items():
            if field == "name":
                redacted += 1
            elif field not in _FIELDS:
                unknown += 1
                partial = True
            elif field == "port":
                if type(value) is int and 0 <= value <= 2**31 - 1:
                    item[field] = value
                else:
                    partial = True
            elif field in _CODES:
                if type(value) is int and 0 <= value <= 2**31 - 1:
                    item[field] = value
                else:
                    partial = True
        if item:
            items.append(item)
        else:
            omitted += 1
            partial = True
    return {"status": "ok", "resource": "gateway_ports", "count": len(items),
            "source_count": len(rows), "items": items, "partial": partial,
            "omitted_count": omitted, "unknown_field_count": unknown,
            "redacted_field_count": redacted}
