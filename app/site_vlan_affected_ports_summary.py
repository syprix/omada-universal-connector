"""Redacted page summary of device and port memberships affected by a VLAN."""
from __future__ import annotations

from typing import Any


class VlanAffectedPortsError(ValueError):
    """Malformed affected-device-port response."""


_DEVICE_TYPES = {"ap", "gateway", "switch", "olt"}
_PORT_FIELDS = {
    "nativePorts": "numeric_port_memberships",
    "tagPorts": "numeric_port_memberships",
    "untagPorts": "numeric_port_memberships",
    "nativeStPorts": "standard_port_memberships",
    "tagStPorts": "standard_port_memberships",
    "untagStPorts": "standard_port_memberships",
    "nativeLags": "lag_memberships",
    "tagLags": "lag_memberships",
    "untagLags": "lag_memberships",
}
_NESTED = {"switchInfo", "esInfo", "stackInfo"}


def project_site_vlan_affected_ports(result: Any, page_number: int,
                                     page_size: int) -> dict[str, object]:
    if (type(page_number) is not int or not 0 <= page_number <= 10_000 or
            type(page_size) is not int or not 1 <= page_size <= 100):
        raise VlanAffectedPortsError("request_invalid")
    if not isinstance(result, dict) or len(result) > 8:
        raise VlanAffectedPortsError("response_invalid")
    rows = result.get("data")
    total = result.get("totalRows")
    current = result.get("currentPage")
    size = result.get("currentSize")
    upstream_page = page_number + 1
    if (not isinstance(rows, list) or len(rows) > page_size or
            type(total) is not int or total < 0 or type(current) is not int or
            current != upstream_page or type(size) is not int or
            not len(rows) <= size <= page_size):
        raise VlanAffectedPortsError("response_invalid")
    if "hasGateway" in result and type(result["hasGateway"]) is not bool:
        raise VlanAffectedPortsError("response_invalid")

    types = {name: 0 for name in sorted(_DEVICE_TYPES)}
    counts = {name: 0 for name in ("numeric_port_memberships",
                                   "standard_port_memberships", "lag_memberships")}
    gateway_ippt = {name: 0 for name in ("supported", "unsupported", "unreported", "invalid")}
    invalid = unknown = missing_port_detail = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 20:
            invalid += 1
            continue
        device_type = row.get("type")
        if not isinstance(device_type, str) or device_type not in _DEVICE_TYPES:
            invalid += 1
            continue
        types[device_type] += 1
        if device_type == "gateway":
            if "gatewayInfo" not in row:
                gateway_ippt["unreported"] += 1
                gateway_info = None
            else:
                gateway_info = row["gatewayInfo"]
            if "gatewayInfo" in row and not isinstance(gateway_info, dict):
                gateway_ippt["invalid"] += 1
                invalid += 1
            elif isinstance(gateway_info, dict):
                if "gatewayDetail" not in gateway_info:
                    gateway_ippt["unreported"] += 1
                    gateway_detail = None
                else:
                    gateway_detail = gateway_info["gatewayDetail"]
                if "gatewayDetail" in gateway_info and not isinstance(gateway_detail, dict):
                    gateway_ippt["invalid"] += 1
                    invalid += 1
                elif isinstance(gateway_detail, dict) and "supportIppt" not in gateway_detail:
                    gateway_ippt["unreported"] += 1
                elif isinstance(gateway_detail, dict) and type(gateway_detail["supportIppt"]) is bool:
                    gateway_ippt["supported" if gateway_detail["supportIppt"]
                                 else "unsupported"] += 1
                elif isinstance(gateway_detail, dict):
                    gateway_ippt["invalid"] += 1
                    invalid += 1
        nested_present = False
        for key in _NESTED:
            if key not in row:
                continue
            nested_present = True
            detail = row[key]
            if not isinstance(detail, dict):
                invalid += 1
                continue
            unknown += len(set(detail) - {"affectedPorts", "clients", "switchDetail",
                                          "esDetail", "stackDetail", "stackLags"})
            ports = detail.get("affectedPorts")
            if ports is None:
                continue
            if not isinstance(ports, dict) or len(ports) > 20:
                invalid += 1
                continue
            unknown += len(set(ports) - set(_PORT_FIELDS) - {"vlan", "ipaddr", "mode"})
            for field, bucket in _PORT_FIELDS.items():
                if field not in ports:
                    continue
                values = ports[field]
                if not isinstance(values, list) or len(values) > 4096:
                    invalid += 1
                    continue
                for value in values:
                    valid = (type(value) is int and 0 <= value <= (1 << 31) - 1) or (
                        isinstance(value, str) and 0 < len(value) <= 64 and
                        value == value.strip() and not any(ord(c) < 32 for c in value))
                    if valid:
                        counts[bucket] += 1
                    else:
                        invalid += 1
        if device_type in {"switch", "olt"} and not nested_present:
            missing_port_detail += 1

    has_more = total > page_number * page_size + len(rows)
    return {
        "page_number": page_number,
        "page_size": page_size,
        "reported_affected_device_count": total,
        "sampled_device_count": len(rows),
        "device_type_counts": types,
        "gateway_ip_passthrough_capability_counts": gateway_ippt,
        **counts,
        "affected_port_membership_count": sum(counts.values()),
        "has_gateway": result.get("hasGateway"),
        "has_more": has_more,
        "missing_port_detail_device_count": missing_port_detail,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(has_more or invalid or unknown or missing_port_detail or
                         gateway_ippt["unreported"]),
        "port_counts_are_memberships_not_unique_physical_ports": True,
    }
