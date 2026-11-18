"""Identity- and address-redacted summary of established IPsec tunnels."""
from __future__ import annotations

from typing import Any


class SiteIpsecTunnelSummaryError(ValueError):
    """Raised when an IPsec tunnel response exceeds its bounded shape."""


_FIELDS = {"site", "name", "id", "status", "direction", "localPeerIp",
           "remotePeerIp", "localSa", "remoteSa"}


def project_site_ipsec_tunnel_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > 500:
        raise SiteIpsecTunnelSummaryError("response_invalid")
    enabled = disabled = status_present = inbound = outbound = direction_present = 0
    invalid = unknown = missing = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 16:
            invalid += 1
            continue
        unknown += len(set(row) - _FIELDS)
        missing += int("status" not in row) + int("direction" not in row)
        if "status" in row:
            if type(row["status"]) is bool:
                status_present += 1
                enabled += int(row["status"])
                disabled += int(not row["status"])
            else:
                invalid += 1
        if "direction" in row:
            if row["direction"] == "in":
                inbound += 1
                direction_present += 1
            elif row["direction"] == "out":
                outbound += 1
                direction_present += 1
            else:
                invalid += 1
        if "id" in row and (type(row["id"]) is not int or not 0 <= row["id"] < 2 ** 31):
            invalid += 1
        for field in ("site", "name", "localPeerIp", "remotePeerIp", "localSa", "remoteSa"):
            if field in row and (not isinstance(row[field], str) or len(row[field]) > 512):
                invalid += 1
    data = {"tunnel_count": len(result), "enabled_tunnel_count": enabled,
            "disabled_tunnel_count": disabled, "status_present_count": status_present,
            "inbound_sa_count": inbound, "outbound_sa_count": outbound,
            "direction_present_count": direction_present}
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
