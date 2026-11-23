"""Counts devices and eligible ports from the port-schedule capability list."""
from __future__ import annotations

from collections.abc import Mapping


class PortSchedulePortsError(ValueError):
    pass


_FIELDS = frozenset(("type", "mac", "name", "site", "model", "modelVersion",
                     "hwVersion", "status", "sn", "ports"))


def summarize_port_schedule_ports(value: object, *, max_items: int = 1000
                                  ) -> dict[str, object]:
    if not isinstance(value, list) or type(max_items) is not int or max_items < 1:
        raise PortSchedulePortsError("invalid device list")
    type_counts = {"gateway": 0, "switch": 0, "unknown": 0}
    port_coverage = {"reported_device_count": 0, "unreported_device_count": 0,
                     "invalid_device_count": 0}
    device_port_count = eligible_port_count = status_reported = 0
    invalid_rows = invalid_fields = unknown_fields = missing_type = 0
    for row in value[:max_items]:
        if not isinstance(row, Mapping) or len(row) > 24:
            invalid_rows += 1
            type_counts["unknown"] += 1
            port_coverage["invalid_device_count"] += 1
            continue
        unknown_fields += sum(key not in _FIELDS for key in row)
        kind = row.get("type")
        if isinstance(kind, str) and kind in {"gateway", "switch"}:
            type_counts[kind] += 1
        elif isinstance(kind, str) and kind:
            type_counts["unknown"] += 1
        else:
            type_counts["unknown"] += 1
            missing_type += 1
        status = row.get("status")
        if status is not None:
            if type(status) is int:
                status_reported += 1
            else:
                invalid_fields += 1
        ports = row.get("ports")
        if not isinstance(ports, Mapping) or len(ports) > 8:
            port_coverage["unreported_device_count"] += 1
            if ports is not None:
                invalid_fields += 1
            continue
        port_num = ports.get("portNum")
        port_ids = ports.get("portIds")
        unknown_fields += sum(key not in {"portNum", "portIds"} for key in ports)
        valid_num = type(port_num) is int and port_num >= 0
        valid_ids = isinstance(port_ids, list) and len(port_ids) <= 512
        if valid_num:
            device_port_count += port_num
        else:
            invalid_fields += 1
        if valid_ids:
            eligible_port_count += len(port_ids)
            if any(type(port) is not int for port in port_ids):
                invalid_fields += 1
        else:
            invalid_fields += 1
        if valid_num and valid_ids:
            port_coverage["reported_device_count"] += 1
        else:
            port_coverage["unreported_device_count"] += 1
    returned = min(len(value), max_items)
    truncated = len(value) > max_items
    return {
        "status": "ok", "resource": "site_port_schedule_ports_summary",
        "reported_device_count": len(value), "returned_device_count": returned,
        "device_type_counts": type_counts, "reported_device_status_field_count": status_reported,
        "device_port_count": device_port_count,
        "schedule_capable_port_count": eligible_port_count,
        "port_data_coverage": port_coverage,
        "invalid_record_count": invalid_rows, "invalid_field_count": invalid_fields,
        "unknown_field_count": unknown_fields, "missing_device_type_count": missing_type,
        "truncated": truncated,
        "partial": bool(invalid_rows or invalid_fields or unknown_fields or missing_type or
                         type_counts["unknown"] or
                         port_coverage["unreported_device_count"] or truncated),
    }
