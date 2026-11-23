"""Redacted counts from the documented v2 VPN client configuration grid."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


class SiteVpnClientConfigSummaryError(ValueError):
    """The VPN client grid does not match its bounded response contract."""


MAX_ROWS = 1_000
VPN_TYPES = {0: "l2tp", 1: "pptp", 3: "openvpn", 4: "wireguard"}
_ALLOWED_FIELDS = {
    "id", "name", "status", "vpnType", "siteVpnType", "wans", "failoverSetting",
    "networkType", "networkList", "customNetwork", "groupId", "userCount",
    "activeClients", "featureDescription",
}


def summarize_vpn_client_config_rows(
        rows: object, omitted_rows: int = 0) -> dict[str, Any]:
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or
            type(omitted_rows) is not int or omitted_rows < 0):
        raise SiteVpnClientConfigSummaryError("input_invalid")

    protocols: Counter[str] = Counter()
    status_flags = {"true": 0, "false": 0, "unreported": 0}
    invalid_rows = unknown_fields = 0
    partial = omitted_rows > 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > len(_ALLOWED_FIELDS):
            invalid_rows += 1
            protocols["unknown"] += 1
            status_flags["unreported"] += 1
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

        flag = row.get("status")
        if type(flag) is bool:
            status_flags["true" if flag else "false"] += 1
        else:
            status_flags["unreported"] += 1
            partial = True

    return {
        "status": "partial" if partial else "ok",
        "resource": "site_vpn_client_config_summary",
        "returned_client_count": len(rows),
        "omitted_client_count": omitted_rows,
        "reported_client_total": len(rows) + omitted_rows,
        "by_documented_protocol": dict(sorted(protocols.items())),
        "by_reported_configuration_flag": status_flags,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial or bool(invalid_rows or unknown_fields),
        "configuration_flag_semantics": "documented boolean VPN status flag; not tunnel connectivity",
        "identities_and_secret_fields_returned": False,
    }
