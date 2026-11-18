"""Redacted counts from the documented all-LAN-networks endpoint."""
from __future__ import annotations

from collections.abc import Mapping


class LanNetworkInventoryError(ValueError):
    """The controller returned an invalid LAN network list."""


_FIELDS = frozenset((
    "id", "site", "name", "purpose", "interfaceIds", "vlanType", "vlans",
    "application", "isolation", "vlan", "gatewaySubnet", "dhcpSettings", "domain",
    "igmpSnoopEnable", "fastLeaveEnable", "mldSnoopEnable", "dhcpv6Guard",
    "dhcpL2RelayEnable", "dhcpGuard", "portal", "portalId", "portalName",
    "accessControlRule", "rateLimit", "lanNeworkIpv6Config", "allLan", "resource",
    "origName", "arpDetectionEnable", "qosQueueEnable", "queueId", "existMultiVlan",
    "existRA", "existCustomDhcpOption", "existDhcpNextServer", "existArpDetection",
    "existNetworkIsolation", "deviceType", "deviceMac", "stackId", "vrfId", "ip",
    "mode", "dhcpServer", "dhcpRelay", "state", "totalIpNum", "dhcpServerNum",
    "dhcpIp", "subnetOverrideEnable", "subnetOverride", "interface", "primary",
))
_BOOLEAN_FIELDS = {
    "isolation": "isolated_network",
    "igmpSnoopEnable": "igmp_snooping",
    "mldSnoopEnable": "mld_snooping",
    "portal": "portal_enabled",
    "arpDetectionEnable": "arp_detection_enabled",
    "accessControlRule": "access_control_rule_enabled",
    "rateLimit": "rate_limit_enabled",
}


def summarize_lan_network_inventory(value: object, *, max_items: int = 500
                                    ) -> dict[str, object]:
    if (not isinstance(value, list) or type(max_items) is not int or max_items <= 0):
        raise LanNetworkInventoryError("invalid LAN network list")
    invalid = unknown = valid = vlan_ids = 0
    purpose_counts = {"vlan": 0, "interface": 0}
    features = {name: {"enabled_count": 0, "disabled_count": 0,
                       "unreported_count": 0} for name in _BOOLEAN_FIELDS.values()}
    dhcp = {"enabled_count": 0, "disabled_count": 0, "unreported_count": 0}
    for row in value[:max_items]:
        if not isinstance(row, Mapping) or len(row) > 64:
            invalid += 1
            continue
        valid += 1
        unknown += sum(key not in _FIELDS for key in row)
        purpose = row.get("purpose")
        if not isinstance(purpose, str) or purpose not in purpose_counts:
            invalid += 1
        else:
            purpose_counts[purpose] += 1
        if "vlan" in row:
            vlan = row["vlan"]
            if type(vlan) is int and 1 <= vlan <= 4094:
                vlan_ids += 1
            else:
                invalid += 1
        for source, output in _BOOLEAN_FIELDS.items():
            counts = features[output]
            if source not in row:
                counts["unreported_count"] += 1
            elif type(row[source]) is bool:
                counts["enabled_count" if row[source] else "disabled_count"] += 1
            else:
                invalid += 1
                counts["unreported_count"] += 1
        settings = row.get("dhcpSettings")
        if settings is None:
            dhcp["unreported_count"] += 1
        elif not isinstance(settings, Mapping) or len(settings) > 16:
            invalid += 1
            dhcp["unreported_count"] += 1
        elif "enable" not in settings:
            dhcp["unreported_count"] += 1
        elif type(settings["enable"]) is bool:
            dhcp["enabled_count" if settings["enable"] else "disabled_count"] += 1
        else:
            invalid += 1
            dhcp["unreported_count"] += 1
    truncated = len(value) > max_items
    return {
        "status": "ok",
        "resource": "site_lan_network_inventory",
        "network_count": len(value),
        "returned_count": min(len(value), max_items),
        "valid_record_count": valid,
        "purpose_counts": purpose_counts,
        "records_with_vlan_id_count": vlan_ids,
        "dhcp_server": dhcp,
        "feature_boolean_counts": features,
        "invalid_record_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(invalid or unknown or truncated),
    }
