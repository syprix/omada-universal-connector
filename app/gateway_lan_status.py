"""Redacted projection of gateway LAN status rows."""
from __future__ import annotations

from typing import Any


class GatewayLanStatusError(ValueError):
    """The gateway LAN-status result cannot be safely bounded."""


_INT32 = 2**31 - 1
_INT64 = 2**63 - 1
_SAFE = frozenset({"vlan", "rx", "tx", "clientNum"})
_REDACTED = frozenset({"lanName", "ip", "lanPortIpv6Config"})


def project_gateway_lan_status(raw: object) -> dict[str, Any]:
    if not isinstance(raw, list) or len(raw) > 64:
        raise GatewayLanStatusError("response_invalid")
    items: list[dict[str, int]] = []
    partial = False
    unknown = redacted = omitted = 0
    for row in raw:
        if not isinstance(row, dict) or len(row) > 32:
            raise GatewayLanStatusError("response_invalid")
        item: dict[str, int] = {}
        for field, value in row.items():
            if field in _REDACTED:
                redacted += 1
            elif field not in _SAFE:
                unknown += 1
                partial = True
            elif field == "vlan":
                if type(value) is int and 0 <= value <= 4094:
                    item[field] = value
                else:
                    partial = True
            elif field == "clientNum":
                if type(value) is int and 0 <= value <= _INT32:
                    item[field] = value
                else:
                    partial = True
            elif type(value) is int and 0 <= value <= _INT64:
                item[field] = value
            else:
                partial = True
        if item:
            items.append(item)
        else:
            omitted += 1
            partial = True
    return {"status": "ok", "resource": "gateway_lan_status", "count": len(items),
            "source_count": len(raw), "items": items, "partial": partial,
            "omitted_count": omitted, "unknown_field_count": unknown,
            "redacted_field_count": redacted}
