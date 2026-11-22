"""Redacted client VPN status-code counts for one selected protocol."""
from __future__ import annotations

from collections import Counter
from typing import Any


class SiteVpnClientStatusSummaryError(ValueError):
    pass


MAX_ROWS = 10_000
VPN_TYPES = {0: "l2tp", 1: "pptp", 3: "openvpn", 4: "wireguard"}
ALLOWED_FIELDS = {
    "id", "vpnId", "spi", "name", "direction", "localPeerIp", "remotePeerIp",
    "localIp", "remoteIp", "localSa", "remoteSa", "protocol", "ahAuthentication",
    "espAuthentication", "espEncryption", "userId", "userName", "interfaceName",
    "serverType", "vpnType", "clientMode", "downPkts", "downBytes", "upPkts",
    "upBytes", "uptime", "dns", "authType", "loginTime", "loginIp", "virtualIp",
    "ipPoolType", "ipPoolStart", "ipPoolEnd", "ipPool", "port", "servicePort",
    "connectedNum", "disconnectedNum", "totalRemoteNum", "status",
}


def summarize_vpn_client_status(rows: list[Any], vpn_type: int) -> dict[str, object]:
    if type(vpn_type) is not int or vpn_type not in VPN_TYPES:
        raise SiteVpnClientStatusSummaryError("vpn_type_invalid")
    if len(rows) > MAX_ROWS:
        raise SiteVpnClientStatusSummaryError("row_limit")
    counts: Counter[str] = Counter()
    missing_status = invalid_rows = unknown_fields = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > len(ALLOWED_FIELDS):
            invalid_rows += 1
            continue
        unknown_fields += len(set(row) - ALLOWED_FIELDS)
        code = row.get("status")
        if isinstance(code, int) and not isinstance(code, bool) and -(2**31) <= code < 2**31:
            counts[str(code)] += 1
        else:
            missing_status += 1
            if code is not None:
                invalid_rows += 1
    return {
        "status": "ok", "resource": "site_vpn_client_status_summary",
        "protocol": VPN_TYPES[vpn_type], "client_row_count": len(rows),
        "by_source_status_code": dict(sorted(counts.items())),
        "missing_status_count": missing_status,
        "unknown_field_count": unknown_fields, "invalid_row_count": invalid_rows,
        "partial": bool(missing_status or unknown_fields or invalid_rows),
        "status_semantics": "source provides an integer code without a code mapping in the three exports",
        "identity_fields_returned": False,
    }
