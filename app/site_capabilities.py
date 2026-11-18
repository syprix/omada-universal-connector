"""Bounded projection for documented site gateway capability flags."""
from __future__ import annotations

from typing import Any


FIELDS = {
    "firewall": "firewall",
    "sslVpn": "ssl_vpn",
    "vpnUser": "vpn_user",
    "oneToOneNat": "one_to_one_nat",
    "disableNat": "disable_nat",
    "ipMacBinding": "ip_mac_binding",
    "qos": "qos",
    "wireguard": "wireguard",
    "dnsProxy": "dns_proxy",
    "ipsecFailover": "ipsec_failover",
    "ldapVpn": "ldap_vpn",
    "serviceType": "qos_service_type",
    "ipsIds": "ids_ips",
    "macFilter": "mac_filtering",
    "sim": "sim",
    "clientRateLimit": "client_rate_limit",
    "lockToAp": "lock_to_ap",
    "voip": "voip",
    "oltVlan": "olt_vlan",
    "p2p": "p2p",
    "serverOpenVpnGoogleLdap": "server_open_vpn_google_ldap",
    "virtualWan": "virtual_wan",
    "l2TP": "l2tp",
    "ipsec": "ipsec",
    "ipPortGroup": "ip_port_group",
    "supportES": "support_es",
    "supportL2": "support_l2",
    "urlCategory": "url_category",
    "customAcl": "custom_acl",
    "peerEndpointDomain": "peer_endpoint_domain",
    "lanDns": "lan_dns",
    "IsolationSettings": "isolation_settings",
    "dsl": "dsl",
    "ldapSsl": "ldap_ssl",
    "googleLdap": "google_ldap",
    "dpi": "dpi",
    "packageCaptureGateway": "package_capture_gateway",
    "cluster": "cluster",
    "clusterModeOn": "cluster_mode_on",
    "initClusterReminder": "init_cluster_reminder",
    "dpiStat": "dpi_stat",
    "serviceIptv": "service_iptv",
    "subVpn": "sub_vpn",
    "vpnStatus": "vpn_status",
    "policyRouting": "policy_routing",
    "supportDpi": "support_dpi",
    "supportShowServerInReservation": "support_show_server_in_reservation",
    "speedTest": "speed_test",
    "natTraversal": "nat_traversal",
}
MAX_SOURCE_FIELDS = 128


class SiteCapabilitiesError(ValueError):
    """Raised when a capability response exceeds the bounded projection."""


def project_site_capabilities(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise SiteCapabilitiesError("response_invalid")
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
    unknown_count = len(set(result) - set(FIELDS))
    missing_count = len(FIELDS) - sum(1 for name in FIELDS if name in result)
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
