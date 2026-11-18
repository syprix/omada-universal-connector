"""Bounded, read-only reconciliation of SSID network bindings."""
from __future__ import annotations

import re
from typing import Callable


_REF = re.compile(r"[0-9a-f]{24}\Z")
_MAX_SSID_DETAILS = 64
_MAX_NETWORK_DETAILS = 32
_MAX_GATEWAY_DETAILS = 4
_MAX_SITE_ITEMS = 10000


class SsidNetworkDiagnoseError(ValueError):
    """Invalid caller input or unsafe inventory response."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _inventory(value: object, *, resource: str, ref_key: str,
               site_ref: str) -> list[str]:
    if (not isinstance(value, dict) or value.get("status") != "ok" or
            value.get("resource") != resource or value.get("site_ref", site_ref) != site_ref):
        raise SsidNetworkDiagnoseError(f"{resource}_inventory_invalid")
    items, count = value.get("items"), value.get("count")
    if (not isinstance(items, list) or len(items) > _MAX_SITE_ITEMS or
            type(count) is not int or count != len(items)):
        raise SsidNetworkDiagnoseError(f"{resource}_inventory_invalid")
    refs: list[str] = []
    for item in items:
        ref = item.get(ref_key) if isinstance(item, dict) else None
        if not isinstance(ref, str) or not _REF.fullmatch(ref):
            raise SsidNetworkDiagnoseError(f"{resource}_inventory_invalid")
        refs.append(ref)
    if len(set(refs)) != len(refs):
        raise SsidNetworkDiagnoseError(f"{resource}_inventory_invalid")
    return refs


def run_site(site_ref: str, requester: Callable[[str], object]) -> dict[str, object]:
    """Compare a bounded set of site SSID config refs with current networks."""
    if not isinstance(site_ref, str) or not _REF.fullmatch(site_ref):
        raise SsidNetworkDiagnoseError("site_ref_invalid")
    if not callable(requester):
        raise SsidNetworkDiagnoseError("connector_unavailable")

    try:
        sites = requester("/v1/sites")
    except Exception:
        raise SsidNetworkDiagnoseError("site_inventory_unavailable") from None
    if (not isinstance(sites, dict) or sites.get("status") != "ok" or
            sites.get("resource") != "sites"):
        raise SsidNetworkDiagnoseError("site_inventory_invalid")
    site_items, site_count = sites.get("items"), sites.get("count")
    if (not isinstance(site_items, list) or len(site_items) > _MAX_SITE_ITEMS or
            type(site_count) is not int or site_count != len(site_items) or
            any(not isinstance(row, dict) or not isinstance(row.get("site_ref"), str) or
                not _REF.fullmatch(row["site_ref"]) for row in site_items)):
        raise SsidNetworkDiagnoseError("site_inventory_invalid")
    if site_ref not in {row["site_ref"] for row in site_items}:
        raise SsidNetworkDiagnoseError("site_ref_unknown")

    root = f"/v1/sites/{site_ref}"
    try:
        ssid_result = requester(root + "/ssids")
    except Exception:
        raise SsidNetworkDiagnoseError("ssid_inventory_unavailable") from None
    ssid_refs = _inventory(ssid_result, resource="ssids", ref_key="ssid_ref", site_ref=site_ref)
    try:
        network_result = requester(root + "/networks")
    except Exception:
        raise SsidNetworkDiagnoseError("network_inventory_unavailable") from None
    network_refs = set(_inventory(
        network_result, resource="networks", ref_key="network_ref", site_ref=site_ref))

    devices_path = root + "/devices"
    try:
        devices_result = requester(devices_path)
    except Exception:
        devices_result = None
    gateway_refs: list[str] = []
    device_inventory_known = False
    unknown_device_type_count = 0
    if (isinstance(devices_result, dict) and devices_result.get("status") == "ok" and
            devices_result.get("resource") == "devices" and
            devices_result.get("site_ref", site_ref) == site_ref and
            isinstance(devices_result.get("items"), list) and
            len(devices_result["items"]) <= _MAX_SITE_ITEMS and
            type(devices_result.get("count")) is int and
            devices_result["count"] == len(devices_result["items"])):
        device_inventory_known = True
        for row in devices_result["items"]:
            if not isinstance(row, dict):
                device_inventory_known = False
                gateway_refs = []
                break
            ref, device_type = row.get("device_ref"), row.get("device_type")
            if not isinstance(ref, str) or not _REF.fullmatch(ref):
                device_inventory_known = False
                gateway_refs = []
                break
            if isinstance(device_type, str) and device_type.strip().casefold() in {
                    "gateway", "router", "gw"}:
                gateway_refs.append(ref)
            elif isinstance(device_type, str) and device_type.strip().casefold() in {
                    "ap", "access point", "accesspoint", "switch", "sw", "olt"}:
                pass
            else:
                unknown_device_type_count += 1

    dns: dict[str, object] = {"status": "unknown"}
    dns_cache_path, dns_proxy_path = root + "/dns/cache", root + "/dns/proxy"
    cache = proxy = cache_data = proxy_data = None
    try:
        cache = requester(dns_cache_path)
        cache_data = cache.get("data") if isinstance(cache, dict) else None
    except Exception:
        pass
    try:
        proxy = requester(dns_proxy_path)
        proxy_data = proxy.get("data") if isinstance(proxy, dict) else None
    except Exception:
        pass
    cache_ok = (isinstance(cache, dict) and cache.get("status") == "ok" and
                cache.get("resource") == "dns_cache_settings" and isinstance(cache_data, dict))
    proxy_ok = (isinstance(proxy, dict) and proxy.get("status") == "ok" and
                proxy.get("resource") == "dns_proxy_settings" and isinstance(proxy_data, dict))
    cache_values: dict[str, object] = {}
    proxy_values: dict[str, object] = {}
    cache_invalid = proxy_invalid = 0
    if cache_ok:
        for source, target, valid in (
                ("enabled", "cache_enabled", lambda value: type(value) is bool),
                ("ttl_seconds", "cache_ttl_seconds",
                 lambda value: type(value) is int and 1 <= value <= 86400)):
            if source in cache_data and valid(cache_data[source]):
                cache_values[target] = cache_data[source]
            elif source in cache_data:
                cache_invalid += 1
    if proxy_ok:
        for source, target, valid in (
                ("enabled", "proxy_enabled", lambda value: type(value) is bool),
                ("mode", "proxy_mode", lambda value: isinstance(value, str) and
                 value in {"dnssec", "doh", "dot", "dns_override"}),
                ("supports_dns_override", "supports_dns_override",
                 lambda value: type(value) is bool),
                ("dns_override_configured", "dns_override_configured",
                 lambda value: type(value) is bool)):
            if source in proxy_data and valid(proxy_data[source]):
                proxy_values[target] = proxy_data[source]
            elif source in proxy_data:
                proxy_invalid += 1
    cache_missing = 2 - len(cache_values)
    proxy_missing = 4 - len(proxy_values)
    cache_status = ("unknown" if not cache_ok or not cache_values else
                    "partial" if cache_missing or cache_invalid or cache.get("partial") is True else
                    "observed")
    proxy_status = ("unknown" if not proxy_ok or not proxy_values else
                    "partial" if proxy_missing or proxy_invalid or proxy.get("partial") is True else
                    "observed")
    dns_status = ("observed" if cache_status == "observed" and proxy_status == "observed" else
                  "partial" if cache_values or proxy_values else "unknown")
    dns = {"status": dns_status, "cache_status": cache_status,
           "proxy_status": proxy_status, "missing_field_count": cache_missing + proxy_missing,
           "invalid_field_count": cache_invalid + proxy_invalid,
           **cache_values, **proxy_values,
           "network_specific_mapping": "unknown"}

    inspected = min(len(ssid_refs), _MAX_SSID_DETAILS)
    matched = unbound = stale = unreadable = 0
    bound_network_refs: set[str] = set()
    for ssid_ref in ssid_refs[:inspected]:
        try:
            detail = requester(f"{root}/ssids/{ssid_ref}")
        except Exception:
            unreadable += 1
            continue
        data = detail.get("data") if isinstance(detail, dict) else None
        binding = data.get("network_binding_ref") if isinstance(data, dict) else None
        if (not isinstance(detail, dict) or detail.get("status") != "ok" or
                detail.get("resource") != "ssid_configuration" or
                detail.get("site_ref", site_ref) != site_ref or
                not isinstance(data, dict) or data.get("ssid_ref") != ssid_ref):
            unreadable += 1
            continue
        if binding is None:
            unbound += 1
        elif not isinstance(binding, str) or not _REF.fullmatch(binding):
            unreadable += 1
        elif binding in network_refs:
            matched += 1
            bound_network_refs.add(binding)
        else:
            stale += 1

    omitted = len(ssid_refs) - inspected
    checked_network_refs = sorted(bound_network_refs)[:_MAX_NETWORK_DETAILS]
    network_details: list[tuple[str, dict[str, object] | None, dict[str, object] | None]] = []
    for network_ref in checked_network_refs:
        try:
            detail = requester(f"{root}/lan-networks/{network_ref}/summary")
        except Exception:
            detail = None
        try:
            dhcp = requester(f"{root}/networks/{network_ref}/dhcp-server/info")
        except Exception:
            dhcp = None
        network_details.append((network_ref, detail if isinstance(detail, dict) else None,
                                dhcp if isinstance(dhcp, dict) else None))

    vlan_values: set[int] = set()
    vlan_observed = 0
    vlan_unknown = vlan_not_applicable = network_detail_failures = network_detail_partial = 0
    dhcp_ranges = dhcp_zero_pool = dhcp_unknown = dhcp_partial = 0
    for network_ref, detail, dhcp in network_details:
        detail_data = detail.get("data") if isinstance(detail, dict) else None
        if (not isinstance(detail, dict) or detail.get("status") != "ok" or
                detail.get("resource") != "site_lan_network_detail_summary" or
                detail.get("site_ref", site_ref) != site_ref or
                detail.get("network_ref", network_ref) != network_ref or
                not isinstance(detail_data, dict)):
            network_detail_failures += 1
            vlan_unknown += 1
        else:
            network_detail_partial += detail.get("partial") is True
            purpose = detail_data.get("purpose_label")
            vlan = detail_data.get("vlan")
            if purpose == "interface":
                vlan_not_applicable += 1
            elif type(vlan) is int and 1 <= vlan <= 4094:
                vlan_observed += 1
                vlan_values.add(vlan)
            else:
                vlan_unknown += 1
        dhcp_data = dhcp.get("data") if isinstance(dhcp, dict) else None
        if (not isinstance(dhcp, dict) or dhcp.get("status") != "ok" or
                dhcp.get("resource") != "network_dhcp_server_info" or
                dhcp.get("site_ref", site_ref) != site_ref or not isinstance(dhcp_data, dict) or
                dhcp.get("network_ref", network_ref) != network_ref or
                type(dhcp_data.get("range_count")) is not int or dhcp_data["range_count"] < 0):
            dhcp_unknown += 1
        else:
            dhcp_ranges += dhcp_data["range_count"]
            dhcp_zero_pool += dhcp_data["range_count"] == 0
            dhcp_partial += dhcp.get("partial") is True

    gateway_checked = 0
    gateway_info_failed = 0
    gateway_info_partial = 0
    if device_inventory_known:
        for gateway_ref in gateway_refs[:_MAX_GATEWAY_DETAILS]:
            gateway_checked += 1
            try:
                info = requester(f"{root}/gateways/{gateway_ref}/internet-info")
            except Exception:
                info = None
            if (not isinstance(info, dict) or info.get("status") != "ok" or
                    info.get("resource") != "gateway_internet_info" or
                    info.get("site_ref", site_ref) != site_ref or
                    info.get("device_ref", gateway_ref) != gateway_ref):
                gateway_info_failed += 1
            else:
                info_data = info.get("data")
                gateway_info_partial += (isinstance(info_data, dict) and
                                         info_data.get("partial") is True)

    return {
        "status": "ok",
        "resource": "ssid_network_summary",
        "ssid_count": len(ssid_refs),
        "network_count": len(network_refs),
        "inspected_count": inspected,
        "matched_count": matched,
        "unbound_count": unbound,
        "stale_binding_count": stale,
        "unreadable_count": unreadable,
        "omitted_count": omitted,
        "network_checks": {
            "checked_network_count": len(checked_network_refs),
            "omitted_network_count": len(bound_network_refs) - len(checked_network_refs),
            "vlan_observed_network_count": vlan_observed,
            "distinct_vlan_count": len(vlan_values),
            "vlan_unknown_network_count": vlan_unknown,
            "vlan_not_applicable_network_count": vlan_not_applicable,
            "network_detail_failure_count": network_detail_failures,
            "network_detail_partial_count": network_detail_partial,
            "dhcp_observed_network_count": len(checked_network_refs) - dhcp_unknown,
            "dhcp_pool_range_count": dhcp_ranges,
            "dhcp_no_pool_observed_network_count": dhcp_zero_pool,
            "dhcp_unknown_network_count": dhcp_unknown,
            "dhcp_partial_network_count": dhcp_partial,
            "dns": dns,
            "device_inventory_status": "observed" if device_inventory_known else "unknown",
            "gateway_inventory_classification": "complete" if device_inventory_known and not unknown_device_type_count else "partial",
            "unknown_device_type_count": unknown_device_type_count,
            "gateway_inventory_count": len(gateway_refs) if device_inventory_known and not unknown_device_type_count else None,
            "gateway_internet_info_checked_count": gateway_checked,
            "gateway_internet_info_omitted_count": max(0, len(gateway_refs) - gateway_checked),
            "gateway_internet_info_failed_count": gateway_info_failed,
            "gateway_internet_info_partial_count": gateway_info_partial,
            "gateway_network_attachment": "unknown",
        },
        "partial": bool(omitted or unreadable or len(bound_network_refs) > len(checked_network_refs)
                        or network_detail_failures or network_detail_partial or vlan_unknown or dhcp_unknown
                        or not device_inventory_known or unknown_device_type_count or
                        len(gateway_refs) > _MAX_GATEWAY_DETAILS or gateway_info_failed or
                        gateway_info_partial
                        or dns.get("status") != "observed"),
    }
