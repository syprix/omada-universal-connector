"""Redacted summary of the paginated v2 site-to-site VPN inventory."""
from __future__ import annotations

from collections.abc import Mapping


class SiteS2SVpnV2SummaryError(ValueError):
    pass


_PAGE_FIELDS = frozenset((
    "totalRows", "currentPage", "currentSize", "data",
    "supportVpnUserTab", "supportCustomDns", "supportCustomNetwork",
    "supportAccountAuth", "supportIpRange", "supportTunnelMode", "supportLdap",
    "supportSslVpnLdap", "supportSslVpnRadius", "supportL2TP", "supportIPsec",
    "supportIPsecIpRange", "supportOpenVpnDomain", "supportWgDomain", "pfsCap",
    "supportServerClientWireGuard", "supportCustomServer", "phase1Proposal1Cap",
    "phase2Proposal2Cap", "supportByDsLiteAndMapE", "supportServerOpenVpnGoogleLdap",
    "supportDnsStatus", "subnetsLimitSize", "wgPeerLimitSize",
    "supportManualWgLocalNetwork", "supportAutoWireGuard", "supportIPsecFailover",
    "sslVpnNum",
))
_ROW_FIELDS = frozenset((
    "id", "name", "status", "vpnType", "siteVpnType", "wans", "failoverSetting",
    "networkType", "networkList", "customNetwork", "groupId", "userCount",
    "activeClients", "featureDescription",
))
_VPN_TYPES = {0: "l2tp", 1: "pptp", 2: "ipsec", 3: "openvpn", 4: "wireguard", 5: "ssl_vpn"}
_CAPABILITY_FLAGS = {
    "supportIPsec": "ipsec",
    "supportAutoWireGuard": "auto_wireguard",
    "supportManualWgLocalNetwork": "manual_wireguard_local_network",
    "supportIPsecFailover": "ipsec_failover",
}


def _value_counts(keys: tuple[str, ...]) -> dict[str, int]:
    return {key: 0 for key in keys}


def summarize_site_s2s_vpn_v2(pages: object, *, max_items: int = 1000) -> dict[str, object]:
    if (not isinstance(pages, list) or not 1 <= len(pages) <= 100 or
            type(max_items) is not int or not 1 <= max_items <= 10_000):
        raise SiteS2SVpnV2SummaryError("invalid page set")

    totals: list[int] = []
    selected: list[object] = []
    missing = invalid = unknown = 0
    support_flags: dict[str, bool | None] = {}
    for page_number, page in enumerate(pages, 1):
        if not isinstance(page, Mapping) or len(page) > 64:
            invalid += 1
            continue
        unknown += sum(key not in _PAGE_FIELDS for key in page)
        total = page.get("totalRows")
        current = page.get("currentPage")
        size = page.get("currentSize")
        rows = page.get("data")
        if type(total) is int and total >= 0:
            totals.append(total)
        else:
            missing += 1 if "totalRows" not in page else 0
            invalid += 1 if "totalRows" in page else 0
        if type(current) is not int or current != page_number:
            missing += 1 if "currentPage" not in page else 0
            invalid += 1 if "currentPage" in page else 0
        if not isinstance(rows, list) or len(rows) > 1000:
            missing += 1 if "data" not in page else 0
            invalid += 1 if "data" in page else 0
            continue
        if type(size) is not int or size not in (len(rows), 100):
            missing += 1 if "currentSize" not in page else 0
            invalid += 1 if "currentSize" in page else 0
        selected.extend(rows)
        if page_number == 1:
            for source, target in _CAPABILITY_FLAGS.items():
                raw = page.get(source)
                if type(raw) is bool:
                    support_flags[target] = raw
                else:
                    support_flags[target] = None
                    missing += 1 if source not in page else 0
                    invalid += 1 if source in page else 0

    if len(set(totals)) > 1:
        invalid += 1
    total_rows = (totals[0] if totals and len(totals) == len(pages) and
                  len(set(totals)) == 1 else None)
    if total_rows is not None and len(selected) > total_rows:
        invalid += 1

    rows = selected[:max_items]
    vpn_types = _value_counts((*[value for value in _VPN_TYPES.values()], "unknown"))
    site_types = _value_counts(("auto", "manual", "unknown"))
    status_flags = _value_counts(("true", "false", "unreported"))
    network_types = _value_counts(("network_list", "custom_network", "unknown"))
    wan_coverage = _value_counts(("with_entries", "empty", "unreported"))
    network_list_coverage = _value_counts(("with_entries", "empty", "unreported"))
    custom_network_coverage = _value_counts(("with_entries", "empty", "unreported"))
    failover_coverage = _value_counts(("object_present", "empty", "unreported"))
    wan_entry_count = network_list_entry_count = custom_network_entry_count = 0
    invalid_records = 0

    def count_string_list(row: Mapping[str, object], field: str,
                          coverage: dict[str, int]) -> int:
        nonlocal invalid
        value = row.get(field)
        if not isinstance(value, list) or len(value) > 512 or any(
                not isinstance(item, str) or len(item) > 128 for item in value):
            coverage["unreported"] += 1
            if value is not None:
                invalid += 1
            return 0
        coverage["with_entries" if value else "empty"] += 1
        return len(value)

    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 32:
            invalid_records += 1
            status_flags["unreported"] += 1
            vpn_types["unknown"] += 1
            site_types["unknown"] += 1
            network_types["unknown"] += 1
            for coverage in (wan_coverage, network_list_coverage,
                             custom_network_coverage, failover_coverage):
                coverage["unreported"] += 1
            continue
        unknown += sum(key not in _ROW_FIELDS for key in row)

        status = row.get("status")
        if type(status) is bool:
            status_flags["true" if status else "false"] += 1
        else:
            status_flags["unreported"] += 1
            invalid += 1 if status is not None else 0

        vpn_type = row.get("vpnType")
        if type(vpn_type) is int and vpn_type in _VPN_TYPES:
            vpn_types[_VPN_TYPES[vpn_type]] += 1
        else:
            vpn_types["unknown"] += 1
            invalid += 1 if vpn_type is not None else 0

        site_type = row.get("siteVpnType")
        if type(site_type) is int and site_type in (0, 1):
            site_types["auto" if site_type == 0 else "manual"] += 1
        else:
            site_types["unknown"] += 1
            invalid += 1 if site_type is not None else 0

        network_type = row.get("networkType")
        if type(network_type) is int and network_type in (0, 1):
            network_types["network_list" if network_type == 0 else "custom_network"] += 1
        else:
            network_types["unknown"] += 1
            invalid += 1 if network_type is not None else 0

        wan_entry_count += count_string_list(row, "wans", wan_coverage)
        network_list_entry_count += count_string_list(
            row, "networkList", network_list_coverage)

        custom = row.get("customNetwork")
        if isinstance(custom, list) and len(custom) <= 512 and all(
                isinstance(item, Mapping) and len(item) <= 8 and
                isinstance(item.get("ip"), str) and type(item.get("mask")) is int
                and 1 <= item.get("mask", 0) <= 32
                for item in custom):
            custom_network_coverage["with_entries" if custom else "empty"] += 1
            custom_network_entry_count += len(custom)
            unknown += sum(key not in {"ip", "mask", "description"}
                           for item in custom for key in item)
        else:
            custom_network_coverage["unreported"] += 1
            invalid += 1 if custom is not None else 0

        failover = row.get("failoverSetting")
        if isinstance(failover, Mapping) and len(failover) <= 8:
            failover_coverage["object_present" if failover else "empty"] += 1
            if any(key not in {"backupWan", "status"} for key in failover):
                unknown += sum(key not in {"backupWan", "status"} for key in failover)
            if ("backupWan" in failover and not isinstance(failover["backupWan"], str)) or (
                    "status" in failover and type(failover["status"]) is not bool):
                invalid += 1
        else:
            failover_coverage["unreported"] += 1
            invalid += 1 if failover is not None else 0

    truncated = ((total_rows is not None and len(selected) < total_rows) or
                 len(selected) > max_items)
    return {
        "resource": "site_s2s_vpn_v2_summary",
        "scope": "configured_site_to_site_vpn_inventory",
        "reported_vpn_count": total_rows,
        "returned_vpn_count": len(rows),
        "vpn_type_counts": vpn_types,
        "site_vpn_type_counts": site_types,
        "reported_status_flag_counts": status_flags,
        "network_type_counts": network_types,
        "wan_assignment_entry_count": wan_entry_count,
        "wan_assignment_coverage_counts": wan_coverage,
        "network_list_entry_count": network_list_entry_count,
        "network_list_coverage_counts": network_list_coverage,
        "custom_network_entry_count": custom_network_entry_count,
        "custom_network_coverage_counts": custom_network_coverage,
        "failover_setting_object_coverage_counts": failover_coverage,
        "capability_support_flags": support_flags,
        "pages_read": len(pages),
        "missing_field_count": missing,
        "invalid_record_count": invalid_records,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "truncated": truncated,
        "partial": bool(missing or invalid_records or invalid or unknown or truncated
                         or total_rows is None or vpn_types["unknown"]
                         or site_types["unknown"] or network_types["unknown"]
                         or status_flags["unreported"]
                         or any(coverage["unreported"] for coverage in (
                             wan_coverage, network_list_coverage,
                             custom_network_coverage, failover_coverage))),
    }
