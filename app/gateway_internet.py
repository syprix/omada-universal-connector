"""Safe projection of documented gateway internet/WAN metadata."""
from __future__ import annotations

import re
from typing import Any


class GatewayInternetError(ValueError):
    """The gateway internet response cannot be safely projected."""


_SUPPORT = frozenset({
    "supportAllWan", "supportCustomInterval", "supportDhcpOptions",
    "supportDiscreteWan", "supportDsLite", "supportDsl", "supportIpv6NonAddress",
    "supportLte", "supportMapE", "supportMssClamping", "supportNetworkIsolation",
    "supportPppoeMru", "supportReduceUsbRfi", "supportTimingMode",
    "supportUsbDhcpOptions", "supportVirtualWan", "supportWanMultipleIp",
})
_REDACTED = frozenset({
    "gatewayMac", "siteId", "omadacId", "portUuids", "networkNames", "unmatchedWans",
    "osgPortInfo", "wanPortSettings", "usbLteSettings", "lteWanSettings", "wanLoadBalance",
})
_KNOWN = _SUPPORT | _REDACTED | {
    "enable", "enableModified", "interval", "unit", "supportMaxWanNum",
    "supportDualSim", "lteIntervalTips", "portOnlineStatus", "resource",
}
_STATUS_ARRAYS = {"wanOnlineStatus": "wan", "virtualWanOnlineStatus": "virtual_wan"}


def _snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _int32(value: object) -> bool:
    return type(value) is int and -(2**31) <= value <= 2**31 - 1


def project_gateway_internet(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or len(raw) > 64:
        raise GatewayInternetError("response_invalid")
    support: dict[str, bool] = {}
    settings: dict[str, int | bool] = {}
    online: dict[str, dict[int, int]] = {}
    partial = False
    unknown = redacted = 0
    for field, value in raw.items():
        if field in _REDACTED:
            redacted += 1
        elif field in _SUPPORT:
            if type(value) is bool:
                support[_snake(field.removeprefix("support"))] = value
            else:
                partial = True
        elif field in {"enable", "enableModified", "lteIntervalTips"}:
            if type(value) is bool:
                settings[{"enable": "internet_enabled", "enableModified": "enable_modified",
                          "lteIntervalTips": "lte_interval_tip"}[field]] = value
            else:
                partial = True
        elif field in {"interval", "unit", "supportMaxWanNum"}:
            if _int32(value):
                settings[{"interval": "interval_code", "unit": "unit_code",
                          "supportMaxWanNum": "max_wan_count"}[field]] = value
            else:
                partial = True
        elif field == "supportDualSim":
            if type(value) is int and value in (0, 1):
                settings["dual_sim_support_code"] = value
            else:
                partial = True
        elif field == "resource":
            if _int32(value):
                settings["resource_code"] = value
            else:
                partial = True
        elif field == "portOnlineStatus":
            if not isinstance(value, dict) or len(value) > 8:
                partial = True
                continue
            extra_groups = set(value) - set(_STATUS_ARRAYS)
            if extra_groups:
                unknown += len(extra_groups)
                partial = True
            for source, family in _STATUS_ARRAYS.items():
                rows = value.get(source)
                if rows is None:
                    continue
                if not isinstance(rows, list) or len(rows) > 64:
                    partial = True
                    continue
                counts = online.setdefault(family, {})
                for row in rows:
                    if not isinstance(row, dict) or len(row) > 8:
                        partial = True
                        continue
                    code = row.get("onlineDetection")
                    if _int32(code):
                        counts[code] = counts.get(code, 0) + 1
                    else:
                        partial = True
                    extra = set(row) - {"onlineDetection", "portUuid", "virtualWanId"}
                    if extra:
                        unknown += len(extra)
                        partial = True
                    redacted += len(set(row) & {"portUuid", "virtualWanId"})
        elif field not in _KNOWN:
            unknown += 1
            partial = True

    return {"status": "ok", "resource": "gateway_internet_info",
            "data": {"support": support, "settings": settings,
                     "online_detection_code_counts": {
                         family: [{"code": code, "count": count}
                                  for code, count in sorted(counts.items())]
                         for family, counts in online.items()},
                     "partial": partial, "unknown_field_count": unknown,
                     "redacted_field_count": redacted}}
