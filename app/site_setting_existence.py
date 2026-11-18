"""Bounded projection for documented site gateway-setting presence flags."""
from __future__ import annotations

from typing import Any


FIELDS = {
    "virtualWan": "virtual_wan",
    "dnsProxy": "dns_proxy",
    "lanDns": "lan_dns",
    "ipsecFailover": "ipsec_failover",
    "wireguard": "wireguard",
    "sslVpn": "ssl_vpn",
    "googleLdap": "google_ldap",
    "ipsIds": "ids_ips",
    "vpnUser": "vpn_user",
    "oneToOneNat": "one_to_one_nat",
    "disableNat": "disable_nat",
    "qos": "qos",
    "serviceType": "qos_service_type",
    "policyRouting": "policy_routing",
    "ipMacBinding": "ip_mac_binding",
    "urlCategory": "url_filtering",
    "dnsCache": "dns_cache",
    "macFilter": "mac_filtering",
}
MAX_SOURCE_FIELDS = 64


class SiteSettingExistenceError(ValueError):
    """Raised when a site-setting response exceeds the bounded projection."""


def project_site_setting_existence(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise SiteSettingExistenceError("response_invalid")
    settings: dict[str, bool] = {}
    invalid_count = 0
    for source, target in FIELDS.items():
        if source not in result:
            continue
        value = result[source]
        if type(value) is bool:
            settings[target] = value
        else:
            invalid_count += 1
    unknown_count = len(set(result) - set(FIELDS))
    missing_count = len(FIELDS) - sum(1 for name in FIELDS if name in result)
    partial = bool(missing_count or invalid_count or unknown_count)
    return {
        "data": {
            "settings": settings,
            "present_count": len(settings),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": partial,
    }
