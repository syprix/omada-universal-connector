"""Identity-free summary of the documented site WAN/LAN metadata response."""
from __future__ import annotations

from typing import Any


class SiteWanLanStatusSummaryError(ValueError):
    """Raised when the upstream WAN/LAN response exceeds its source bounds."""


_ROOT_FIELDS = {"portName", "networkComptent", "adoptedGateway", "supportIpv6",
                "wanList", "iptvPorts", "preOsgModel", "model", "modelVersion",
                "hasGateway"}
_WAN_FIELDS = {"portId", "portName", "enable", "networkId", "proto", "pdEnable",
               "prefix", "pdSize"}
_STRING_ROOT = {"model", "modelVersion"}
_INT32_MAX = (1 << 31) - 1
_MAX_PORTS = 64


def _int32(value: Any) -> bool:
    return type(value) is int and 0 <= value <= _INT32_MAX


def project_site_wan_lan_status_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 16:
        raise SiteWanLanStatusSummaryError("wan_lan_status_invalid")

    invalid = unknown = 0
    unknown += len(set(result) - _ROOT_FIELDS)
    for key in _STRING_ROOT:
        if key in result and not isinstance(result[key], str):
            invalid += 1
    for key in ("networkComptent", "supportIpv6", "preOsgModel"):
        if key in result and not _int32(result[key]):
            invalid += 1
    for key in ("adoptedGateway", "hasGateway"):
        if key in result and type(result[key]) is not bool:
            invalid += 1

    wan_list = result.get("wanList")
    wan_count: int | None = None
    if "wanList" in result:
        if not isinstance(wan_list, list) or len(wan_list) > _MAX_PORTS:
            invalid += 1
        else:
            wan_count = len(wan_list)
            for row in wan_list:
                if not isinstance(row, dict) or len(row) > 16:
                    invalid += 1
                    continue
                unknown += len(set(row) - _WAN_FIELDS)
                for key in ("portId", "portName", "networkId", "prefix"):
                    if key in row and not isinstance(row[key], str):
                        invalid += 1
                for key in ("enable", "proto", "pdEnable", "pdSize"):
                    if key in row and not _int32(row[key]):
                        invalid += 1

    iptv_ports = result.get("iptvPorts")
    iptv_count: int | None = None
    if "iptvPorts" in result:
        if not isinstance(iptv_ports, list) or len(iptv_ports) > _MAX_PORTS:
            invalid += 1
        else:
            iptv_count = len(iptv_ports)
            invalid += sum(not isinstance(port, str) for port in iptv_ports)

    names = result.get("portName")
    named_port_count: int | None = None
    if "portName" in result:
        if not isinstance(names, dict) or len(names) > _MAX_PORTS:
            invalid += 1
        else:
            named_port_count = len(names)
            invalid += sum(not isinstance(key, str) or not isinstance(value, str)
                           for key, value in names.items())

    data = {
        "gateway_adopted": result.get("adoptedGateway")
        if type(result.get("adoptedGateway")) is bool else None,
        "gateway_or_wan_override_present": result.get("hasGateway")
        if type(result.get("hasGateway")) is bool else None,
        "ipv6_support_code": result.get("supportIpv6")
        if _int32(result.get("supportIpv6")) else None,
        "network_component_present": "networkComptent" in result,
        "wan_port_count": wan_count,
        "iptv_port_count": iptv_count,
        "named_port_count": named_port_count,
    }
    return {"data": data, "missing_field_count": 0,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(invalid or unknown)}
