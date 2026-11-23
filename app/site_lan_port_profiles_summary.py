"""Redacted aggregate of documented site LAN port profile settings."""
from __future__ import annotations

from collections.abc import Mapping


class SiteLanPortProfilesError(ValueError):
    pass


_ENUMS = {
    "type": {0, 1, 2}, "flag": {0, 1, 2}, "networkTagsSetting": {0, 1, 2},
    "poe": {0, 1, 2}, "dot1x": {0, 1, 2}, "bandWidthCtrlType": {0, 1, 2},
}
_BOOLS = (
    "prohibitModify", "vlanConfigEnable", "voiceNetworkEnable", "voiceDscpEnable",
    "esEnable", "esTaggedModified", "portIsolationEnable", "lldpMedEnable",
    "topoNotifyEnable", "spanningTreeEnable", "loopbackDetectEnable", "eeeEnable",
    "flowControlEnable", "loopbackDetectVlanBasedEnable", "igmpFastLeaveEnable",
    "mldFastLeaveEnable", "fastLeaveEnable", "createByNewUI",
)
_INTS = ("nativeBridgeVlan", "voiceBridgeVlan", "voiceDscp", "dot1pPriority",
         "trustMode", "resource")
_STRINGS = ("id", "nativeNetworkId", "voiceNetworkId", "name")
_ARRAYS = ("tagNetworkIds", "untagNetworkIds", "esEnableTaggedNetworkIds")
_OBJECTS = ("tagBridgeVlanMap", "untagBridgeVlanMap", "esEnableTagBridgeVlanMap",
            "stormCtrl", "bandCtrl", "spanningTreeSetting", "dhcpL2RelaySettings")
_REQUIRED = {"bandWidthCtrlType", "dot1x", "lldpMedEnable", "loopbackDetectEnable",
             "name", "networkTagsSetting", "poe", "portIsolationEnable",
             "spanningTreeEnable", "vlanConfigEnable"}


def project_site_lan_port_profiles(rows: object, total: object,
                                   pages_fetched: int, page_limit: int) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 1_000 or type(total) is not int or
            total < len(rows) or not 0 <= total < (1 << 63) or
            type(pages_fetched) is not int or not 0 <= pages_fetched <= 10 or
            type(page_limit) is not int or not 1 <= page_limit <= 10):
        raise SiteLanPortProfilesError("input_invalid")
    known = set(_ENUMS) | set(_BOOLS) | set(_INTS) | set(_STRINGS) | set(_ARRAYS) | set(_OBJECTS)
    enum_counts = {field: {} for field in _ENUMS}
    bool_counts = {field: {"true": 0, "false": 0, "unknown": 0} for field in _BOOLS}
    partial = len(rows) < total
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 64:
            raise SiteLanPortProfilesError("row_invalid")
        if set(row) - known:
            partial = True
        if _REQUIRED - set(row):
            partial = True
        for field in _STRINGS:
            if field in row and (not isinstance(row[field], str) or len(row[field]) > 512):
                raise SiteLanPortProfilesError("field_invalid")
        for field in _ARRAYS:
            if field in row and (not isinstance(row[field], list) or len(row[field]) > 4_096 or
                                 any(not isinstance(value, str) or len(value) > 512
                                     for value in row[field])):
                raise SiteLanPortProfilesError("field_invalid")
        for field in _OBJECTS:
            if field in row and (not isinstance(row[field], Mapping) or len(row[field]) > 128):
                raise SiteLanPortProfilesError("field_invalid")
        for field in _INTS:
            if field in row and (type(row[field]) is not int or
                                 not -(1 << 31) <= row[field] < (1 << 31)):
                raise SiteLanPortProfilesError("field_invalid")
        for field, values in _ENUMS.items():
            value = row.get(field)
            if value is None:
                enum_counts[field].setdefault("unknown", 0)
                enum_counts[field]["unknown"] += 1
                partial = True
                continue
            if type(value) is not int or value not in values:
                raise SiteLanPortProfilesError("field_invalid")
            enum_counts[field][str(value)] = enum_counts[field].get(str(value), 0) + 1
        for field in _BOOLS:
            if field not in row:
                bool_counts[field]["unknown"] += 1
            elif type(row[field]) is not bool:
                raise SiteLanPortProfilesError("field_invalid")
            else:
                bool_counts[field]["true" if row[field] else "false"] += 1
    return {
        "profile_count": len(rows),
        "total_count": total,
        "coverage_complete": len(rows) >= total,
        "profile_enum_counts": enum_counts,
        "feature_enabled_counts": bool_counts,
        "pages_fetched": pages_fetched,
        "page_limit": page_limit,
        "partial": partial,
        "profile_names_and_ids_returned": False,
        "device_assignment_inferred": False,
    }
