"""Redacted projection for the documented WAN-port availability response."""
from __future__ import annotations

from typing import Mapping


class WanPortAvailabilityError(ValueError):
    pass


def project_wan_port_availability(result: object, function: int) -> dict[str, object]:
    if type(function) is not int or function not in range(16):
        raise WanPortAvailabilityError("function_invalid")
    if not isinstance(result, Mapping) or len(result) > 16:
        raise WanPortAvailabilityError("result_invalid")

    partial = (any(key not in {"enable", "wanPorts"} for key in result) or
               "enable" not in result)
    enabled = result.get("enable")
    if enabled is not None and type(enabled) is not bool:
        raise WanPortAvailabilityError("enable_invalid")
    rows = result.get("wanPorts")
    if rows is None:
        return {
            "function": function, "enabled": enabled, "listed_port_count": None,
            "qos_configured_count": None, "qos_configured_count_known": 0,
            "ipv6_enabled_count": None, "ipv6_enabled_count_known": 0,
            "iptv_supported_count": None, "iptv_supported_count_known": 0,
            "recommended_count": None, "recommended_count_known": 0,
            "partial": True,
        }
    if not isinstance(rows, list) or len(rows) > 256:
        raise WanPortAvailabilityError("ports_invalid")

    configured = ipv6 = iptv = recommended = 0
    known_configured = known_ipv6 = known_iptv = known_recommended = 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 32:
            raise WanPortAvailabilityError("port_invalid")
        allowed = {"portName", "portUuid", "type", "configured", "supportIptv",
                   "virtualWanNum", "proto", "ipv6", "ipv6Proto", "recommendedWan", "ip"}
        partial |= bool(set(row) - allowed)
        for key in ("portName", "portUuid", "proto", "ipv6Proto", "ip"):
            value = row.get(key)
            if value is not None and (not isinstance(value, str) or len(value) > 256):
                raise WanPortAvailabilityError("port_field_invalid")
        wan_type = row.get("type")
        if wan_type is not None and (type(wan_type) is not int or
                                     not -(2**31) <= wan_type <= 2**31 - 1):
            raise WanPortAvailabilityError("wan_type_invalid")
        for key, counter in (("configured", "configured"), ("ipv6", "ipv6"),
                             ("supportIptv", "iptv"), ("recommendedWan", "recommended")):
            value = row.get(key)
            if value is not None and type(value) is not bool:
                raise WanPortAvailabilityError("port_flag_invalid")
            if value is None:
                partial = True
                continue
            if counter == "configured":
                known_configured += 1
                configured += value
            elif counter == "ipv6":
                known_ipv6 += 1
                ipv6 += value
            elif counter == "iptv":
                known_iptv += 1
                iptv += value
            else:
                known_recommended += 1
                recommended += value
        virtual_count = row.get("virtualWanNum")
        if virtual_count is not None and (type(virtual_count) is not int or
                                           not 0 <= virtual_count <= 2**31 - 1):
            raise WanPortAvailabilityError("virtual_wan_count_invalid")

    return {
        "function": function,
        "enabled": enabled,
        "listed_port_count": len(rows),
        "qos_configured_count": configured,
        "qos_configured_count_known": known_configured,
        "ipv6_enabled_count": ipv6,
        "ipv6_enabled_count_known": known_ipv6,
        "iptv_supported_count": iptv,
        "iptv_supported_count_known": known_iptv,
        "recommended_count": recommended,
        "recommended_count_known": known_recommended,
        "partial": partial,
    }
