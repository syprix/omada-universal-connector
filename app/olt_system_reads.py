"""Bounded projections for documented OLT system GET responses."""
from __future__ import annotations

from typing import Any


MAX_INT32 = 2_147_483_647
MAX_INT64 = 9_223_372_036_854_775_807
_SYSTEM_FIELDS = {
    "systemDescription", "deviceName", "deviceLocation", "contactInformation",
    "mac", "serialNumber", "hardwareVersion", "firmwareVersion",
    "bootLoaderVersion", "systemTime", "runningTime", "jumboFrameStatus",
    "sntpStatus", "igmpSnoopingStatus", "snmpStatus", "spanningTreeStatus",
    "dhcpRelayStatus", "httpServerStatus", "telnetStatus", "sshStatus",
}
_STATUS_FIELDS = {
    "jumboFrameStatus": "jumbo_frame_enabled",
    "sntpStatus": "time_sync_enabled",
    "igmpSnoopingStatus": "igmp_snooping_enabled",
    "snmpStatus": "snmp_enabled",
    "spanningTreeStatus": "spanning_tree_enabled",
    "dhcpRelayStatus": "dhcp_relay_enabled",
    "httpServerStatus": "http_server_enabled",
    "telnetStatus": "telnet_enabled",
    "sshStatus": "ssh_enabled",
}
_INTERFACE_TYPES = {"MANAGEMENT", "NONE", "VLAN", "ROUTED_PORT", "PORT_CHANNEL"}
_INTERFACE_FIELDS = {"interfaceId", "interfaceType", "interfaceValue"}


class OltSystemReadError(ValueError):
    """Raised when a documented OLT system response exceeds its schema bounds."""


def _int(value: Any, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _bool_status(value: Any) -> bool | None:
    if type(value) is int and value in (0, 1):
        return value == 1
    return None


def project_olt_system_info(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        raise OltSystemReadError("response_invalid")
    known = _SYSTEM_FIELDS
    data: dict[str, object] = {}
    missing = 0
    invalid = 0
    unknown = len(set(result) - known)
    for source in ("systemDescription", "deviceName", "deviceLocation", "contactInformation",
                   "mac", "serialNumber", "hardwareVersion", "firmwareVersion",
                   "bootLoaderVersion", "systemTime"):
        value = result.get(source)
        if value is None:
            missing += 1
        elif isinstance(value, str):
            # Preserve only presence: these fields can carry identifiers, contact data,
            # addresses, timestamps, or free-form descriptions.
            data[source + "_present"] = bool(value)
        else:
            invalid += 1
    uptime = result.get("runningTime")
    if uptime is None:
        missing += 1
    elif _int(uptime, MAX_INT64):
        data["uptime_seconds"] = uptime
    else:
        invalid += 1
    for source, target in _STATUS_FIELDS.items():
        value = result.get(source)
        if value is None:
            missing += 1
        else:
            status = _bool_status(value)
            if status is None:
                invalid += 1
            else:
                data[target] = status
    return {"data": data, "partial": bool(missing or invalid or unknown),
            "missing_count": missing, "invalid_count": invalid,
            "unknown_field_count": unknown}


def project_olt_management_interfaces(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        raise OltSystemReadError("response_invalid")
    unknown = len(set(result) - {"systemInterfaces"})
    interfaces = result.get("systemInterfaces")
    missing = int("systemInterfaces" not in result or interfaces is None)
    invalid = 0
    if interfaces is None:
        interfaces = []
    if not isinstance(interfaces, list) or len(interfaces) > 16:
        raise OltSystemReadError("response_invalid")
    type_counts: dict[str, int] = {}
    value_present_count = 0
    id_present_count = 0
    for row in interfaces:
        if not isinstance(row, dict):
            invalid += 1
            continue
        unknown += len(set(row) - _INTERFACE_FIELDS)
        interface_type = row.get("interfaceType")
        if isinstance(interface_type, str) and interface_type in _INTERFACE_TYPES:
            type_counts[interface_type] = type_counts.get(interface_type, 0) + 1
        else:
            invalid += 1
        interface_id = row.get("interfaceId")
        if interface_id is not None:
            if _int(interface_id, 3):
                id_present_count += 1
            else:
                invalid += 1
        value = row.get("interfaceValue")
        if value is not None:
            if isinstance(value, str):
                value_present_count += int(bool(value))
            else:
                invalid += 1
        elif interface_type != "NONE":
            missing += 1
    return {
        "data": {"interface_count": len(interfaces), "type_counts": type_counts,
                 "interface_id_present_count": id_present_count,
                 "interface_value_present_count": value_present_count},
        "partial": bool(missing or invalid or unknown), "missing_count": missing,
        "invalid_count": invalid, "unknown_field_count": unknown,
    }
