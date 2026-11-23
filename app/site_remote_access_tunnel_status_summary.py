"""Redacted connection and open-state counts for remote-access tunnels."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


class RemoteAccessTunnelStatusSummaryError(ValueError):
    """The source response exceeds the bounded documented row contract."""


MAX_ROWS = 1024
STATUSES = {
    0: "disconnected", 1: "connected", 2: "opening",
    -1: "heartbeat_missed", -2: "expired",
}
_ALLOWED_FIELDS = {"tunnelId", "status", "openStatus", "name"}


def summarize_remote_access_tunnel_status(
        rows: object) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise RemoteAccessTunnelStatusSummaryError("rows_invalid")

    selected = rows[:MAX_ROWS]
    omitted = max(0, len(rows) - len(selected))
    status_counts: Counter[str] = Counter()
    open_status = {"open": 0, "closed": 0, "unreported": 0}
    invalid_rows = unknown_fields = 0
    partial = omitted > 0
    for row in selected:
        if not isinstance(row, Mapping) or len(row) > len(_ALLOWED_FIELDS):
            invalid_rows += 1
            status_counts["unknown"] += 1
            open_status["unreported"] += 1
            partial = True
            continue
        row_unknown = sum(key not in _ALLOWED_FIELDS for key in row)
        unknown_fields += row_unknown
        if row_unknown:
            partial = True
        status = row.get("status")
        if type(status) is int and status in STATUSES:
            status_counts[STATUSES[status]] += 1
        else:
            status_counts["unknown"] += 1
            partial = True
        opened = row.get("openStatus")
        if type(opened) is bool:
            open_status["open" if opened else "closed"] += 1
        else:
            open_status["unreported"] += 1
            partial = True

    return {
        "status": "partial" if partial or invalid_rows or unknown_fields else "ok",
        "resource": "site_remote_access_tunnel_status_summary",
        "reported_tunnel_count": len(rows),
        "summarized_tunnel_count": len(selected),
        "omitted_tunnel_count": omitted,
        "by_documented_connection_status": dict(sorted(status_counts.items())),
        "by_documented_open_status": open_status,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": bool(partial or invalid_rows or unknown_fields),
        "identity_fields_returned": False,
    }
