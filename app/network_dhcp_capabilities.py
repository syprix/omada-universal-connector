"""Bounded projection for documented per-network DHCP server capabilities."""
from __future__ import annotations

from typing import Any


FIELDS = {
    "supportGetDhcpClientTable": "get_dhcp_client_table",
    "supportGetDhcpServerInfo": "get_dhcp_server_info",
}
MAX_SOURCE_FIELDS = 16


class NetworkDhcpCapabilitiesError(ValueError):
    """Raised when a DHCP capability response exceeds its bounded projection."""


def project_network_dhcp_capabilities(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise NetworkDhcpCapabilitiesError("response_invalid")
    capabilities: dict[str, bool] = {}
    invalid_count = 0
    for source, target in FIELDS.items():
        if source not in result:
            continue
        value = result[source]
        if type(value) is bool:
            capabilities[target] = value
        else:
            invalid_count += 1
    missing_count = len(FIELDS) - sum(name in result for name in FIELDS)
    unknown_count = len(set(result) - set(FIELDS))
    return {
        "data": {
            "capabilities": capabilities,
            "present_count": len(capabilities),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
