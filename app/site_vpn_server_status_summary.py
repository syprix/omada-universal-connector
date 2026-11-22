"""Redacted status-code counts for one selected VPN server protocol."""
from __future__ import annotations

from collections import Counter
from typing import Any


class SiteVpnServerStatusSummaryError(ValueError):
    pass


MAX_ROWS = 10_000
VPN_TYPES = {0: "l2tp", 1: "pptp", 2: "ipsec", 3: "openvpn", 4: "wireguard", 5: "ssl_vpn"}


def summarize_vpn_server_status(rows: list[Any], vpn_type: int) -> dict[str, object]:
    if type(vpn_type) is not int or vpn_type not in VPN_TYPES:
        raise SiteVpnServerStatusSummaryError("vpn_type_invalid")
    if len(rows) > MAX_ROWS:
        raise SiteVpnServerStatusSummaryError("row_limit")
    status_counts: Counter[str] = Counter()
    missing_status = invalid_rows = unknown_fields = 0
    allowed = {"id", "vpnId", "spi", "name", "direction", "localPeerIp", "remotePeerIp",
               "localIp", "remoteIp", "localSa", "remoteSa", "protocol", "ahAuthentication",
               "espAuthentication", "espEncryption", "userId", "userName", "interfaceName",
               "serverType", "vpnType", "clientMode", "downPkts", "downBytes", "upPkts",
               "upBytes", "uptime", "dns", "authType", "loginTime", "loginIp", "virtualIp",
               "ipPoolType", "ipPoolStart", "ipPoolEnd", "ipPool", "port", "servicePort",
               "connectedNum", "disconnectedNum", "totalRemoteNum", "status"}
    for row in rows:
        if not isinstance(row, dict) or len(row) > len(allowed):
            invalid_rows += 1
            continue
        unknown_fields += len(set(row) - allowed)
        status = row.get("status")
        if isinstance(status, int) and not isinstance(status, bool) and -(2**31) <= status < 2**31:
            status_counts[str(status)] += 1
        else:
            missing_status += 1
            if status is not None:
                invalid_rows += 1
    return {
        "status": "ok", "resource": "site_vpn_server_status_summary",
        "protocol": VPN_TYPES[vpn_type], "server_row_count": len(rows),
        "by_source_status_code": dict(sorted(status_counts.items())),
        "missing_status_count": missing_status,
        "unknown_field_count": unknown_fields, "invalid_row_count": invalid_rows,
        "partial": bool(missing_status or unknown_fields or invalid_rows),
        "status_semantics": "source provides an integer code without a code mapping in the three exports",
        "identity_fields_returned": False,
    }
