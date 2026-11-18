"""Redacted diagnostic summary for one LAN network."""

from __future__ import annotations

from collections.abc import Mapping
import ipaddress
import re
from typing import Any


class SiteLanNetworkDetailSummaryError(ValueError):
    """The LAN network detail response is outside its documented bounds."""


_FIELDS = frozenset({
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
})
_ENUMS = {
    "purpose": {0: "vlan", 1: "interface"},
    "vlanType": {0: "single", 1: "multiple"},
    "application": {0: "gateway_and_switch", 1: "switch"},
    "deviceType": {0: "external", 1: "gateway", 2: "switch", 3: "none"},
}
_BOOLS = (
    "isolation", "igmpSnoopEnable", "fastLeaveEnable", "mldSnoopEnable",
    "portal", "accessControlRule", "rateLimit", "arpDetectionEnable",
    "dhcpL2RelayEnable", "allLan", "qosQueueEnable", "existMultiVlan",
    "existRA", "existCustomDhcpOption", "existDhcpNextServer",
    "existArpDetection", "existNetworkIsolation", "subnetOverrideEnable", "primary",
)
_INT32_MIN, _INT32_MAX = -(2**31), 2**31 - 1
_MAX_VLAN_TEXT = 4096
_MAX_POOL_RANGES = 256
_DHCP_FIELDS = frozenset({"enable", "ipRangePool", "ipRangeStart", "ipRangeEnd", "dhcpns", "priDns", "sndDns", "leasetime", "gateway", "dhcpNextServer", "dhcpPoolMask", "options"})
_POOL_FIELDS = frozenset({"ipaddrStart", "ipaddrEnd"})
_REDACTED_FIELDS = frozenset({"id", "site", "name", "interfaceIds", "vlans", "domain", "dhcpv6Guard", "portalId", "portalName", "origName", "deviceMac", "stackId", "ip", "dhcpServer", "dhcpRelay", "dhcpIp", "subnetOverride"})


def _int32(value: Any) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def _bool(value: Any) -> bool:
    return type(value) is bool


def _vlan_summary(value: Any) -> tuple[dict[str, int] | None, bool]:
    if not isinstance(value, str) or len(value) > _MAX_VLAN_TEXT:
        return None, False
    if not value:
        return {"vlan_count": 0, "range_count": 0}, True
    total = ranges = 0
    for item in value.split(","):
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", item)
        if not match:
            return None, False
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if not (1 <= start <= end <= 4094):
            return None, False
        total += end - start + 1
        ranges += 1
    return {"vlan_count": total, "range_count": ranges}, True


def project_site_lan_network_detail(value: Any) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 128:
        raise SiteLanNetworkDetailSummaryError("result_invalid")
    unknown = sum(key not in _FIELDS for key in value)
    # ER7212PC's export omits `name` and `deviceType` from the required list;
    # only fields required consistently across the three source contracts
    # contribute to the missing-field signal.
    missing = sum(key not in value or value[key] is None
                  for key in ("purpose", "igmpSnoopEnable"))
    invalid = 0
    partial = bool(unknown or missing)
    if "name" in value and value["name"] is not None and not isinstance(value["name"], str):
        invalid += 1
        partial = True
    redacted = sum(key in value and value[key] not in (None, "", [], {})
                   for key in _REDACTED_FIELDS)
    data: dict[str, object] = {"unknown_field_count": unknown,
                               "missing_field_count": missing,
                               "invalid_field_count": 0,
                               "redacted_field_count": redacted}

    for key, labels in _ENUMS.items():
        if key not in value or value[key] is None:
            continue
        code = value[key]
        if not _int32(code):
            invalid += 1
            partial = True
            continue
        label = labels.get(code)
        out_key = re.sub(r"([A-Z])", r"_\1", key).lower()
        data[out_key + "_code"] = code
        data[out_key + "_label"] = label
        if label is None:
            invalid += 1
            partial = True

    for source in _BOOLS:
        if source not in value or value[source] is None:
            continue
        if _bool(value[source]):
            data[re.sub(r"([A-Z])", r"_\1", source).lower()] = value[source]
        else:
            invalid += 1
            partial = True

    vlan = value.get("vlan")
    if vlan is not None:
        if _int32(vlan) and 1 <= vlan <= 4094:
            data["vlan"] = vlan
        else:
            invalid += 1
            partial = True
    vlan_type = value.get("vlanType")
    if vlan_type == 1 and "vlans" in value:
        compact, valid = _vlan_summary(value["vlans"])
        if value["vlans"] not in (None, ""):
            redacted += 1
        if valid:
            data["multi_vlan_summary"] = compact
        else:
            invalid += 1
            partial = True

    subnet = value.get("gatewaySubnet")
    if subnet is not None:
        if isinstance(subnet, str) and len(subnet) <= 64:
            try:
                data["gateway_subnet"] = str(ipaddress.IPv4Interface(subnet))
            except ValueError:
                invalid += 1
                partial = True
        else:
            invalid += 1
            partial = True

    dhcp = value.get("dhcpSettings")
    if dhcp is not None:
        if not isinstance(dhcp, Mapping) or len(dhcp) > 32:
            invalid += 1
            partial = True
        else:
            dhcp_summary: dict[str, object] = {}
            dhcp_unknown = sum(key not in _DHCP_FIELDS for key in dhcp)
            if dhcp_unknown:
                unknown += dhcp_unknown
                partial = True
            if "enable" in dhcp:
                if _bool(dhcp["enable"]):
                    dhcp_summary["enabled"] = dhcp["enable"]
                else:
                    invalid += 1
                    partial = True
            redacted += sum(key in dhcp and dhcp[key] not in (None, "", [], {})
                            for key in _DHCP_FIELDS - {"enable", "ipRangePool"})
            pool = dhcp.get("ipRangePool")
            if pool is not None:
                if isinstance(pool, list) and len(pool) <= _MAX_POOL_RANGES:
                    dhcp_summary["pool_range_count"] = len(pool)
                    for row in pool:
                        if not isinstance(row, Mapping):
                            invalid += 1
                            partial = True
                            continue
                        extra_pool = sum(key not in _POOL_FIELDS for key in row)
                        if extra_pool:
                            unknown += extra_pool
                            partial = True
                        redacted += sum(key in row and row[key] not in (None, "")
                                        for key in _POOL_FIELDS)
                        if any(key not in row or not isinstance(row[key], str)
                               for key in _POOL_FIELDS):
                            invalid += 1
                            partial = True
                else:
                    invalid += 1
                    partial = True
            if dhcp_summary:
                data["dhcp"] = dhcp_summary

    data["invalid_field_count"] = invalid
    data["redacted_field_count"] = redacted
    return {"data": data, "partial": partial}
