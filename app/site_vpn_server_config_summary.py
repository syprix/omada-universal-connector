"""Redacted counts from the documented v2 client-to-site VPN server grid."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


class ControllerVpnServerConfigSummaryError(ValueError):
    """The grid rows do not match the documented, bounded response shape."""


VPN_TYPES = {
    0: "l2tp", 1: "pptp", 2: "ipsec", 3: "openvpn", 4: "wireguard", 5: "ssl_vpn",
}
_ALLOWED_FIELDS = {
    "id", "name", "status", "vpnType", "siteVpnType", "wans", "failoverSetting",
    "networkType", "networkList", "customNetwork", "groupId", "userCount",
    "activeClients", "featureDescription",
}


def summarize_vpn_server_config_rows(
        rows: object, omitted_rows: int = 0) -> dict[str, Any]:
    if (not isinstance(rows, list) or len(rows) > 1000 or
            type(omitted_rows) is not int or omitted_rows < 0):
        raise ControllerVpnServerConfigSummaryError("input_invalid")

    protocols: Counter[str] = Counter()
    activation = {"enabled": 0, "disabled": 0, "unreported": 0}
    invalid_rows = unknown_fields = 0
    partial = omitted_rows > 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > len(_ALLOWED_FIELDS):
            invalid_rows += 1
            activation["unreported"] += 1
            partial = True
            continue
        row_unknown_fields = sum(key not in _ALLOWED_FIELDS for key in row)
        unknown_fields += row_unknown_fields
        if row_unknown_fields:
            partial = True
        vpn_type = row.get("vpnType")
        if type(vpn_type) is int and vpn_type in VPN_TYPES:
            protocols[VPN_TYPES[vpn_type]] += 1
        else:
            protocols["unknown"] += 1
            partial = True
        status = row.get("status")
        if type(status) is bool:
            activation["enabled" if status else "disabled"] += 1
        else:
            activation["unreported"] += 1
            partial = True

    return {
        "status": "partial" if partial else "ok",
        "resource": "site_vpn_server_config_summary",
        "returned_server_count": len(rows),
        "omitted_server_count": omitted_rows,
        "reported_server_total": len(rows) + omitted_rows,
        "by_documented_protocol": dict(sorted(protocols.items())),
        "by_reported_activation_flag": activation,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial or bool(invalid_rows or unknown_fields),
        "activation_semantics": "documented VPN status flag; not tunnel connectivity",
        "identity_and_secret_fields_returned": False,
    }
