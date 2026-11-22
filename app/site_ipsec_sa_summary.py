"""Redacted IPsec security-association counts from the documented grid read."""
from __future__ import annotations

from collections import Counter
from typing import Any


class SiteIpsecSaSummaryError(ValueError):
    pass


MAX_ROWS = 10_000
_STRING_FIELDS = {
    "name", "direction", "localPeerIp", "remotePeerIp", "localSa", "remoteSa",
    "protocol", "ahAuthentication", "espAuthentication", "espEncryption",
}
_FIELDS = _STRING_FIELDS | {"vpnId", "spi"}


def summarize_site_ipsec_associations(rows: list[Any]) -> dict[str, object]:
    if len(rows) > MAX_ROWS:
        raise SiteIpsecSaSummaryError("row_limit")
    directions: Counter[str] = Counter()
    invalid_rows = invalid_fields = unknown_fields = redacted_fields = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 16:
            invalid_rows += 1
            continue
        unknown_fields += len(set(row) - _FIELDS)
        bad = False
        for field in _STRING_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and len(value) <= 4096:
                if field in row and value:
                    redacted_fields += 1
            elif field in row and value is not None:
                invalid_fields += 1
                bad = True
        for field, maximum in (("vpnId", 2**31 - 1), ("spi", 2**63 - 1)):
            value = row.get(field)
            if (value is not None and
                    (not isinstance(value, int) or isinstance(value, bool)
                     or value < 0 or value > maximum)):
                invalid_fields += 1
                bad = True
            elif field in row and value is not None:
                redacted_fields += 1
        direction = row.get("direction")
        directions[direction if isinstance(direction, str) and direction in {"in", "out"}
                   else "unknown"] += 1
        if bad:
            invalid_rows += 1
    return {
        "status": "ok", "resource": "site_ipsec_sa_summary",
        "security_association_count": len(rows),
        "by_direction": dict(sorted(directions.items())),
        "missing_direction_count": directions.get("unknown", 0),
        "invalid_row_count": invalid_rows,
        "invalid_field_count": invalid_fields,
        "unknown_field_count": unknown_fields,
        "redacted_field_count": redacted_fields,
        "partial": bool(invalid_rows or invalid_fields or unknown_fields or directions.get("unknown")),
        "connection_status": "not provided by the source contract; tunnel state is unknown",
    }
