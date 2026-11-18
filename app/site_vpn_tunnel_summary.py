"""Redacted aggregate VPN tunnel status and byte counters."""
from __future__ import annotations

from typing import Any


class SiteVpnTunnelSummaryError(ValueError):
    """Raised when the unpaged VPN statistics response is malformed or oversized."""


_FIELDS = {"site", "name", "status", "tunnels", "txData", "rxData"}
_MAX_ROWS = 500
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1


def project_site_vpn_tunnel_summary(result: Any, vpn_type: int) -> dict[str, object]:
    if type(vpn_type) is not int or vpn_type not in (0, 1):
        raise SiteVpnTunnelSummaryError("request_invalid")
    if not isinstance(result, list) or len(result) > _MAX_ROWS:
        raise SiteVpnTunnelSummaryError("response_invalid")
    counts = {key: 0 for key in ("status", "tunnels", "txData", "rxData")}
    totals = {key: 0 for key in ("tunnels", "txData", "rxData")}
    complete = {key: True for key in counts}
    invalid = unknown = missing = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 12:
            invalid += 1
            for key in complete:
                complete[key] = False
            continue
        unknown += len(set(row) - _FIELDS)
        for key in ("site", "name"):
            if key in row and not isinstance(row[key], str):
                invalid += 1
        for key in counts:
            if key not in row:
                missing += 1
                complete[key] = False
                continue
            value = row[key]
            if key == "status":
                if type(value) is not bool:
                    invalid += 1
                    complete[key] = False
                else:
                    counts[key] += int(value)
            else:
                upper = _INT32_MAX if key == "tunnels" else _INT64_MAX
                if type(value) is not int or not 0 <= value <= upper:
                    invalid += 1
                    complete[key] = False
                else:
                    totals[key] += value
    data: dict[str, object] = {
        "vpn_type": "server" if vpn_type == 0 else "client",
        "vpn_count": len(result),
        "enabled_vpn_count": counts["status"] if complete["status"] else None,
        "disabled_vpn_count": (len(result) - counts["status"]
                               if complete["status"] else None),
        "total_tunnel_count": totals["tunnels"] if complete["tunnels"] else None,
        "total_tx_bytes": totals["txData"] if complete["txData"] else None,
        "total_rx_bytes": totals["rxData"] if complete["rxData"] else None,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
    }
    return {"data": data, "partial": bool(missing or invalid or unknown or
                                             not all(complete.values()))}
