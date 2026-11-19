"""Redacted VLAN support-port counts from the documented controller result."""
from __future__ import annotations


class VlanPortSupportError(ValueError):
    """Invalid or unsafe controller response."""


_DEVICE_TYPES = {"gateway", "switch", "ap", "olt"}


def project_site_vlan_port_support_summary(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict) or set(raw) - {"devicePortSupportVlan"}:
        raise VlanPortSupportError("support_result_invalid")
    devices = raw.get("devicePortSupportVlan")
    if not isinstance(devices, dict):
        raise VlanPortSupportError("support_devices_invalid")
    single_device_shape = "type" in devices
    rows = [("", devices)] if single_device_shape else list(devices.items())
    if len(rows) > 10_000:
        raise VlanPortSupportError("support_devices_invalid")
    device_type_counts = {name: 0 for name in sorted(_DEVICE_TYPES)}
    ports_by_device_type = {name: {"supported": 0, "unsupported": 0, "unknown": 0}
                            for name in sorted(_DEVICE_TYPES)}
    device_count = reported_port_count = supported = unsupported = unknown_support = 0
    invalid = unknown_fields = redacted = devices_without_ports = 0
    partial_shape = single_device_shape
    for key, device in rows:
        if not isinstance(key, str) or not isinstance(device, dict):
            raise VlanPortSupportError("support_device_invalid")
        device_count += 1
        allowed_device = {"mac", "type", "portList", "stackId"}
        unknown_fields += len(set(device) - allowed_device)
        redacted += sum(field in device and device[field] is not None for field in ("mac", "stackId"))
        device_type = device.get("type")
        if not isinstance(device_type, str) or device_type not in _DEVICE_TYPES:
            invalid += 1
            continue
        device_type_counts[device_type] += 1
        ports = device.get("portList")
        if ports is None:
            devices_without_ports += 1
            continue
        if not isinstance(ports, list) or len(ports) > 10_000:
            invalid += 1
            continue
        for port in ports:
            if not isinstance(port, dict):
                invalid += 1
                continue
            reported_port_count += 1
            allowed_port = {"port", "standardPort", "lagId", "mlagId", "support"}
            unknown_fields += len(set(port) - allowed_port)
            redacted += sum(field in port and port[field] is not None
                            for field in ("port", "standardPort", "lagId", "mlagId"))
            value = port.get("support")
            if type(value) is not bool:
                unknown_support += 1
                ports_by_device_type[device_type]["unknown"] += 1
            elif value:
                supported += 1
                ports_by_device_type[device_type]["supported"] += 1
            else:
                unsupported += 1
                ports_by_device_type[device_type]["unsupported"] += 1
    partial = bool(invalid or unknown_fields or unknown_support or devices_without_ports or partial_shape)
    return {
        "device_count": device_count,
        "device_type_counts": device_type_counts,
        "reported_port_count": reported_port_count,
        "supported_port_count": supported,
        "unsupported_port_count": unsupported,
        "unknown_support_port_count": unknown_support,
        "port_counts_by_device_type": ports_by_device_type,
        "devices_without_port_list_count": devices_without_ports,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown_fields,
        "redacted_field_count": redacted,
        "partial": partial,
        "coverage": ("single_device_object_shape; source provides no total-coverage field"
                     if single_device_shape else
                     "returned_rows_only; source provides no total-coverage field"),
    }
