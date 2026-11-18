"""Bounded projection for site multicast/broadcast packet-rate settings."""
from __future__ import annotations

from typing import Any


class SiteMulticastRateLimitError(ValueError):
    """Raised when the multicast rate-limit response is outside its shape bound."""


_ENABLE_FIELDS = {
    "enable": "enabled",
    "arpEnable": "arp_enabled",
    "ndEnable": "nd_enabled",
    "igmpEnable": "igmp_enabled",
    "dhcpEnable": "dhcp_enabled",
    "dhcpv6Enable": "dhcpv6_enabled",
    "mdnsEnable": "mdns_enabled",
    "otherBcastEnable": "other_broadcast_enabled",
    "otherMcastEnable": "other_multicast_enabled",
}
_RATE_FIELDS = {
    "arpPps": "arp_packets_per_second",
    "ndPps": "nd_packets_per_second",
    "igmpPps": "igmp_packets_per_second",
    "dhcpPps": "dhcp_packets_per_second",
    "dhcpv6Pps": "dhcpv6_packets_per_second",
    "mdnsPps": "mdns_packets_per_second",
    "otherBcastPps": "other_broadcast_packets_per_second",
    "otherMcastPps": "other_multicast_packets_per_second",
}
_FIELDS = set(_ENABLE_FIELDS) | set(_RATE_FIELDS)


def project_site_multicast_rate_limit(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise SiteMulticastRateLimitError("response_invalid")
    missing = int("mcastRateLimit" not in result)
    invalid = 0
    unknown = len(set(result) - {"mcastRateLimit"})
    data: dict[str, object] = {}
    config = result.get("mcastRateLimit")
    if "mcastRateLimit" in result:
        if not isinstance(config, dict) or len(config) > 24:
            invalid += 1
        else:
            unknown += len(set(config) - _FIELDS)
            enabled_count = 0
            switch_count = 0
            for field, output in _ENABLE_FIELDS.items():
                if field not in config:
                    continue
                value = config[field]
                if type(value) is bool:
                    data[output] = value
                    enabled_count += int(value and field != "enable")
                    switch_count += 1
                else:
                    invalid += 1
            for field, output in _RATE_FIELDS.items():
                if field not in config:
                    continue
                value = config[field]
                if type(value) is int and -(2 ** 31) <= value < 2 ** 31:
                    data[output] = value
                else:
                    invalid += 1
            data["enabled_limiter_count"] = enabled_count
            data["valid_switch_count"] = switch_count
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
