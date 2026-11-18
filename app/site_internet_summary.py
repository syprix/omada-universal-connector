"""Redacted summary of site-level Internet/WAN settings."""

from __future__ import annotations

from collections.abc import Mapping


class SiteInternetSummaryError(ValueError):
    """The controller response has an invalid shape."""


_SUPPORT_FLAGS = (
    "supportCustomInterval", "supportDiscreteWan", "supportReduceUsbRfi",
    "supportAllWan", "supportIpv6NonAddress", "supportMssClamping",
    "supportPppoeMru", "supportWanMultipleIp", "supportLte", "supportDsl",
    "supportVirtualWan", "supportNetworkIsolation", "supportDhcpOptions",
    "supportUsbDhcpOptions", "supportDsLite", "supportMapE", "supportTimingMode",
)
_TOP_FIELDS = frozenset((
    "omadacId", "siteId", "enable", "osgPortInfo", "portUuids", "interval", "unit",
    *_SUPPORT_FLAGS, "supportMaxWanNum", "supportDualSim", "wanPortSettings",
    "usbLteSettings", "lteWanSettings", "wanLoadBalance", "networkNames",
    "unmatchedWans", "gatewayMac", "enableModified", "lteIntervalTips",
    "portOnlineStatus", "resource", "supportDualSim", "preOsgModelName",
))
_ARRAY_FIELDS = ("wanPortSettings", "usbLteSettings", "lteWanSettings", "networkNames",
                 "unmatchedWans", "portUuids")
_MAX_I32 = 2_147_483_647


def _optional_i32(result: Mapping[str, object], key: str, counters: list[int]) -> int | None:
    if key not in result:
        counters[0] += 1
        return None
    value = result[key]
    if not isinstance(value, int) or isinstance(value, bool) or not -(2**31) <= value <= _MAX_I32:
        counters[1] += 1
        return None
    return value


def _count_array(result: Mapping[str, object], key: str, counters: list[int]) -> int | None:
    if key not in result:
        counters[0] += 1
        return None
    value = result[key]
    if not isinstance(value, list) or len(value) > 256:
        counters[1] += 1
        return None
    return len(value)


def project_site_internet(result: object) -> dict[str, object]:
    """Project only bounded counts and safe flags; omit all network identities/secrets."""
    if not isinstance(result, Mapping) or len(result) > 96:
        raise SiteInternetSummaryError("result must be a bounded object")
    counters = [0, 0]  # missing, invalid
    unknown = sum(key not in _TOP_FIELDS for key in result)

    site_id = result.get("siteId")
    if "siteId" not in result:
        counters[0] += 1
    elif not isinstance(site_id, str):
        counters[1] += 1

    enabled = result.get("enable")
    if "enable" not in result:
        counters[0] += 1
        enabled = None
    elif not isinstance(enabled, bool):
        counters[1] += 1
        enabled = None

    counts = {key: _count_array(result, key, counters) for key in _ARRAY_FIELDS}
    # Names and UUIDs are only counted internally; they are never returned.
    wan_count = counts["wanPortSettings"]
    usb_count = counts["usbLteSettings"]
    lte_count = counts["lteWanSettings"]
    unmatched_count = counts["unmatchedWans"]

    osg = result.get("osgPortInfo")
    gateway_wan_port_count: int | None = None
    if "osgPortInfo" not in result:
        counters[0] += 1
    elif not isinstance(osg, Mapping) or len(osg) > 32:
        counters[1] += 1
    else:
        unknown += sum(k not in {"realOsgModel", "preOsgModel", "preOsgModelName",
                                 "targetModels", "wanPortNum", "wanLanPortSettings"}
                       for k in osg)
        value = osg.get("wanPortNum")
        if "wanPortNum" not in osg:
            counters[0] += 1
        elif not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= _MAX_I32:
            counters[1] += 1
        else:
            gateway_wan_port_count = value
        if "wanLanPortSettings" in osg and (
                not isinstance(osg["wanLanPortSettings"], list) or
                len(osg["wanLanPortSettings"]) > 256):
            counters[1] += 1

    support_flags: dict[str, bool | None] = {}
    for key in _SUPPORT_FLAGS:
        value = result.get(key)
        if key not in result:
            counters[0] += 1
            support_flags[key.removeprefix("support")] = None
        elif not isinstance(value, bool):
            counters[1] += 1
            support_flags[key.removeprefix("support")] = None
        else:
            support_flags[key.removeprefix("support")] = value

    load_balance = result.get("wanLoadBalance")
    app_optimized: bool | None = None
    link_backup: bool | None = None
    weight_count: int | None = None
    if "wanLoadBalance" not in result:
        counters[0] += 1
    elif not isinstance(load_balance, Mapping) or len(load_balance) > 32:
        counters[1] += 1
    else:
        unknown += sum(k not in {"weights", "appOptRouting", "linkBackup", "method",
                                 "primaryWans", "backupWan", "backupMode", "mode",
                                 "timeRangeId", "virtualWanWeights"} for k in load_balance)
        for key, target in (("appOptRouting", "app_optimized_routing"),
                            ("linkBackup", "link_backup_enabled")):
            value = load_balance.get(key)
            if key not in load_balance:
                counters[0] += 1
            elif not isinstance(value, bool):
                counters[1] += 1
            if target == "app_optimized_routing":
                app_optimized = value if isinstance(value, bool) else None
            else:
                link_backup = value if isinstance(value, bool) else None
        weights = load_balance.get("weights")
        if not isinstance(weights, list) or len(weights) > 256:
            if "weights" not in load_balance:
                counters[0] += 1
            else:
                counters[1] += 1
        else:
            weight_count = len(weights)

    online = result.get("portOnlineStatus")
    wan_status_count: int | None = None
    virtual_status_count: int | None = None
    if "portOnlineStatus" not in result:
        counters[0] += 1
    elif not isinstance(online, Mapping) or len(online) > 8:
        counters[1] += 1
    else:
        unknown += sum(k not in {"virtualWanOnlineStatus", "wanOnlineStatus"} for k in online)
        for key, target in (("wanOnlineStatus", "wan"),
                            ("virtualWanOnlineStatus", "virtual")):
            value = online.get(key)
            if key not in online:
                counters[0] += 1
            elif not isinstance(value, list) or len(value) > 256:
                counters[1] += 1
            elif target == "wan":
                wan_status_count = len(value)
            else:
                virtual_status_count = len(value)

    interval = _optional_i32(result, "interval", counters)
    unit = _optional_i32(result, "unit", counters)
    support_max = _optional_i32(result, "supportMaxWanNum", counters)
    dual_sim = _optional_i32(result, "supportDualSim", counters)
    resource = _optional_i32(result, "resource", counters)
    return {
        "data": {
            "enabled": enabled,
            "configured_wan_port_count": wan_count,
            "configured_usb_lte_port_count": usb_count,
            "configured_lte_wan_count": lte_count,
            "gateway_wan_port_count": gateway_wan_port_count,
            "unmatched_wan_count": unmatched_count,
            "wan_status_entry_count": wan_status_count,
            "virtual_wan_status_entry_count": virtual_status_count,
            "load_balance": {
                "app_optimized_routing": app_optimized,
                "link_backup_enabled": link_backup,
                "weight_entry_count": weight_count,
            },
            "support_flags": support_flags,
            "max_wan_count_supported": support_max,
            "dual_sim_support_code": dual_sim,
            "interval": interval,
            "interval_unit_code": unit,
            "resource_code": resource,
        },
        "missing_field_count": counters[0], "invalid_field_count": counters[1],
        "unknown_field_count": unknown,
        "partial": bool(counters[0] or counters[1] or unknown),
    }
