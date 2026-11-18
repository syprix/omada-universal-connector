"""Bounded, redacted feature counts for site LAN-network configuration."""

from __future__ import annotations

from collections.abc import Mapping


class SiteLanNetworkSummaryError(ValueError):
    """The controller returned an invalid LAN-network page listing."""


_PAGE_FIELDS = frozenset((
    "totalRows", "currentPage", "currentSize", "data", "supportMultiVlan",
    "supportRA", "supportCustomDhcpOption", "combinedGateway", "dhcpRangePoolSize",
    "interfaceNum", "supportDefault", "osgSupportIgmpSnooping",
    "supportDhcpNextServer", "vlanNums", "supportArpDetection",
    "supportNetworkIsolation", "supportLanIpv6", "supportLanIpv6PassThrough",
    "supportMaxVlanNum", "supportPdOnDhcp",
))
_ROW_FIELDS = frozenset((
    "id", "site", "name", "purpose", "interfaceIds", "vlanType", "vlans",
    "application", "isolation", "vlan", "gatewaySubnet", "dhcpSettings", "domain",
    "igmpSnoopEnable", "fastLeaveEnable", "mldSnoopEnable", "dhcpv6Guard",
    "dhcpL2RelayEnable", "dhcpGuard", "portal", "portalId", "portalName",
    "accessControlRule", "rateLimit", "lanNeworkIpv6Config", "allLan", "resource",
    "origName", "arpDetectionEnable", "qosQueueEnable", "queueId", "existMultiVlan",
    "existRA", "existCustomDhcpOption", "existDhcpNextServer", "existArpDetection",
    "existNetworkIsolation", "deviceType", "deviceMac", "stackId", "ip", "mode",
    "vrfId", "dhcpServer", "dhcpRelay", "dhcpIp", "state", "totalIpNum",
    "dhcpServerNum", "subnetOverrideEnable", "subnetOverride", "primary",
))
_FEATURE_FIELDS = {
    "isolation": "isolated_network",
    "allLan": "all_lan_network",
    "igmpSnoopEnable": "igmp_snooping",
    "fastLeaveEnable": "igmp_fast_leave",
    "mldSnoopEnable": "mld_snooping",
    "dhcpL2RelayEnable": "dhcp_l2_relay",
    "portal": "portal_enabled",
    "accessControlRule": "access_control_rule_enabled",
    "rateLimit": "rate_limit_enabled",
    "arpDetectionEnable": "arp_detection_enabled",
    "qosQueueEnable": "qos_queue_enabled",
    "existMultiVlan": "multi_vlan_configured",
    "existRA": "router_advertisement_configured",
    "existCustomDhcpOption": "custom_dhcp_options_configured",
    "existDhcpNextServer": "dhcp_next_server_configured",
    "existArpDetection": "arp_detection_configured",
    "existNetworkIsolation": "network_isolation_configured",
    "subnetOverrideEnable": "subnet_override_enabled",
    "subnetOverride": "subnet_override",
    "primary": "primary_network",
}


def project_site_lan_networks(pages: object) -> dict[str, object]:
    """Aggregate documented purpose and Boolean feature counts from up to 500 rows."""
    if not isinstance(pages, list) or not 1 <= len(pages) <= 5:
        raise SiteLanNetworkSummaryError("pages must contain one to five bounded pages")

    missing = invalid = unknown = returned = valid = unknown_purpose = 0
    totals: list[int] = []
    purpose_counts = {"0": 0, "1": 0}
    purpose_complete = True
    features = {name: {"enabled_count": 0, "disabled_count": 0,
                       "unreported_count": 0}
                for name in _FEATURE_FIELDS.values()}
    for expected_page, page in enumerate(pages, 1):
        if not isinstance(page, Mapping) or len(page) > 32:
            invalid += 1
            continue
        unknown += sum(key not in _PAGE_FIELDS for key in page)
        for field in ("totalRows", "currentPage", "currentSize", "data"):
            if field not in page:
                missing += 1
        total, current_page = page.get("totalRows"), page.get("currentPage")
        if type(total) is int and total >= 0:
            totals.append(total)
        elif "totalRows" in page:
            invalid += 1
        if type(current_page) is not int or current_page != expected_page:
            if "currentPage" in page:
                invalid += 1
        rows = page.get("data")
        if not isinstance(rows, list) or len(rows) > 100:
            if "data" in page:
                invalid += 1
            continue
        current_size = page.get("currentSize")
        if type(current_size) is not int or current_size != len(rows):
            invalid += 1
        returned += len(rows)
        for row in rows:
            if not isinstance(row, Mapping) or len(row) > 64:
                invalid += 1
                purpose_complete = False
                for counts in features.values():
                    counts["unreported_count"] += 1
                continue
            valid += 1
            unknown += sum(key not in _ROW_FIELDS for key in row)
            purpose = row.get("purpose")
            if "purpose" not in row:
                missing += 1
                purpose_complete = False
            elif type(purpose) is not int:
                invalid += 1
                purpose_complete = False
            elif str(purpose) in purpose_counts:
                purpose_counts[str(purpose)] += 1
            else:
                unknown_purpose += 1
                purpose_complete = False
            for source_field, output_field in _FEATURE_FIELDS.items():
                counts = features[output_field]
                if source_field not in row:
                    counts["unreported_count"] += 1
                elif type(row[source_field]) is not bool:
                    invalid += 1
                    counts["unreported_count"] += 1
                elif row[source_field]:
                    counts["enabled_count"] += 1
                else:
                    counts["disabled_count"] += 1

    total = totals[0] if totals and len(totals) == len(pages) and len(set(totals)) == 1 else None
    if len(set(totals)) > 1 or (total is not None and returned > total):
        invalid += 1
    truncated = (total > returned if total is not None else
                 len(pages) == 5 and all(isinstance(p, Mapping) and
                                         isinstance(p.get("data"), list) and
                                         len(p["data"]) == 100 for p in pages))
    return {
        "data": {
            "reported_total_network_count": total,
            "returned_network_count": returned,
            "valid_network_record_count": valid,
            "purpose_code_counts": purpose_counts if purpose_complete else None,
            "unknown_purpose_code_count": unknown_purpose,
            "feature_boolean_counts": features,
            "pages_read": len(pages),
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or unknown_purpose or truncated),
    }
