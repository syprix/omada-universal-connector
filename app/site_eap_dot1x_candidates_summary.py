"""Redacted, bounded summary of site EAP 802.1X port candidates."""
from __future__ import annotations

from typing import Any


class EapDot1xCandidatesError(ValueError):
    """The controller candidate list is outside its documented shape."""


_DEVICE_FIELDS = frozenset({"name", "mac", "model", "version", "status",
                            "statusCategory", "ports"})
_PORT_FIELDS = frozenset({"port", "dot1xEnable", "mabEnable", "supportDot1x"})
_STATUS_CATEGORIES = frozenset({0, 1, 2, 3, 4})
MAX_DEVICES = 5_000
MAX_PORTS_PER_DEVICE = 256
MAX_STRING_LENGTH = 512


def _valid_text(value: object, limit: int = MAX_STRING_LENGTH) -> bool:
    return (isinstance(value, str) and len(value) <= limit and
            all(ord(char) >= 32 and ord(char) != 127 for char in value))


def summarize_site_eap_dot1x_candidates(raw: object) -> dict[str, Any]:
    """Return counts only; names, MACs, models, firmware and port numbers are dropped."""
    if not isinstance(raw, list):
        raise EapDot1xCandidatesError("candidate_list_invalid")

    rows = raw[:MAX_DEVICES]
    status_counts: dict[str, int] = {}
    port_flags = {
        "dot1x_enabled": {"true": 0, "false": 0},
        "mab_enabled": {"true": 0, "false": 0},
        "dot1x_supported": {"true": 0, "false": 0},
    }
    valid_devices = invalid = unknown = redacted = 0
    known_status = unknown_status = 0
    returned_port_count = processed_port_count = valid_ports = 0
    unknown_port_flag_count = 0
    truncated_ports = 0
    port_coverage_unknown_devices = 0

    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            invalid += 1
            continue
        valid_devices += 1
        unknown += sum(key not in _DEVICE_FIELDS for key in row)
        for key in ("name", "mac", "model", "version", "status"):
            if key in row:
                redacted += 1
                if not _valid_text(row[key]):
                    invalid += 1

        if "statusCategory" in row:
            value = row["statusCategory"]
            if type(value) is int and value in _STATUS_CATEGORIES:
                status_counts[str(value)] = status_counts.get(str(value), 0) + 1
                known_status += 1
            elif type(value) is int:
                unknown_status += 1
            else:
                invalid += 1
                unknown_status += 1
        else:
            unknown_status += 1

        if "ports" not in row:
            unknown += 1
            continue
        ports = row["ports"]
        if not isinstance(ports, list):
            invalid += 1
            continue
        returned_port_count += len(ports)
        if len(ports) >= MAX_PORTS_PER_DEVICE:
            port_coverage_unknown_devices += 1
        if len(ports) > MAX_PORTS_PER_DEVICE:
            truncated_ports += len(ports) - MAX_PORTS_PER_DEVICE
            ports = ports[:MAX_PORTS_PER_DEVICE]
        processed_port_count += len(ports)
        for port in ports:
            if not isinstance(port, dict) or len(port) > 16:
                invalid += 1
                continue
            valid_ports += 1
            unknown += sum(key not in _PORT_FIELDS for key in port)
            if "port" in port:
                redacted += 1
                if not _valid_text(port["port"], 64):
                    invalid += 1
            for key, output in (("dot1xEnable", "dot1x_enabled"),
                                ("mabEnable", "mab_enabled"),
                                ("supportDot1x", "dot1x_supported")):
                if key not in port:
                    unknown_port_flag_count += 1
                    continue
                value = port[key]
                if type(value) is not bool:
                    invalid += 1
                    unknown_port_flag_count += 1
                    continue
                port_flags[output][str(value).lower()] += 1

    truncated_devices = len(raw) > MAX_DEVICES
    coverage_unknown = (len(raw) >= MAX_DEVICES or
                        port_coverage_unknown_devices > 0)
    return {
        "returned_device_count": len(raw),
        "processed_device_count": len(rows),
        "valid_device_count": valid_devices,
        "status_category_counts": status_counts,
        "devices_with_known_status_category": known_status,
        "unknown_status_category_count": unknown_status,
        "returned_port_count": returned_port_count,
        "processed_port_count": processed_port_count,
        "valid_port_count": valid_ports,
        "port_feature_counts": port_flags,
        "unknown_port_feature_count": unknown_port_flag_count,
        "truncated_device_rows": max(0, len(raw) - MAX_DEVICES),
        "truncated": bool(truncated_devices or truncated_ports),
        "truncated_port_rows": truncated_ports,
        "port_coverage_unknown_devices": port_coverage_unknown_devices,
        "coverage_unknown": coverage_unknown,
        "redacted_field_count": redacted,
        "unknown_field_count": unknown,
        "invalid_field_count": invalid,
        "partial": bool(invalid or unknown or unknown_status or
                         unknown_port_flag_count or truncated_devices or truncated_ports or
                         coverage_unknown),
    }


_SWITCH_FIELDS = frozenset({
    "name", "mac", "model", "version", "status", "statusCategory", "addedInAdvanced",
    "ports", "supportVrf", "accountVrfId", "authVrfId", "supportSingleMabAuth",
    "portConfigured",
})
_SWITCH_PORT_FIELDS = frozenset({"port", "dot1xEnable", "mabEnable", "authType", "operation", "lag"})


def summarize_site_switch_dot1x_candidates(raw: object) -> dict[str, Any]:
    """Summarize switch authentication candidates without identifiers or port details."""
    if not isinstance(raw, list):
        raise EapDot1xCandidatesError("candidate_list_invalid")

    rows = raw[:MAX_DEVICES]
    status_counts: dict[str, int] = {}
    auth_type_counts: dict[str, int] = {}
    device_flags = {
        key: {"true": 0, "false": 0}
        for key in ("added_in_advanced", "vrf_supported", "single_mab_supported", "port_configured")
    }
    port_flags = {
        key: {"true": 0, "false": 0}
        for key in ("dot1x_enabled", "mab_enabled", "lag")
    }
    invalid = unknown = redacted = 0
    valid_switches = valid_ports = processed_ports = returned_ports = 0
    unknown_status = unknown_port_flags = unknown_device_flags = unknown_auth_types = 0
    truncated_ports = port_coverage_unknown_switches = 0

    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            invalid += 1
            continue
        valid_switches += 1
        unknown += sum(key not in _SWITCH_FIELDS for key in row)
        for key in ("name", "mac", "model", "version", "status", "accountVrfId", "authVrfId"):
            if key in row:
                redacted += 1
                if not _valid_text(row[key]):
                    invalid += 1

        if "statusCategory" not in row:
            unknown_status += 1
        elif type(row["statusCategory"]) is int and row["statusCategory"] in _STATUS_CATEGORIES:
            key = str(row["statusCategory"])
            status_counts[key] = status_counts.get(key, 0) + 1
        elif type(row["statusCategory"]) is int:
            unknown_status += 1
        else:
            invalid += 1
            unknown_status += 1

        for source, output in (("addedInAdvanced", "added_in_advanced"),
                               ("supportVrf", "vrf_supported"),
                               ("supportSingleMabAuth", "single_mab_supported"),
                               ("portConfigured", "port_configured")):
            if source not in row:
                unknown_device_flags += 1
            elif type(row[source]) is bool:
                device_flags[output][str(row[source]).lower()] += 1
            else:
                invalid += 1
                unknown_device_flags += 1

        if "ports" not in row:
            unknown += 1
            continue
        ports = row["ports"]
        if not isinstance(ports, list):
            invalid += 1
            continue
        returned_ports += len(ports)
        if len(ports) >= MAX_PORTS_PER_DEVICE:
            port_coverage_unknown_switches += 1
        if len(ports) > MAX_PORTS_PER_DEVICE:
            truncated_ports += len(ports) - MAX_PORTS_PER_DEVICE
            ports = ports[:MAX_PORTS_PER_DEVICE]
        processed_ports += len(ports)
        for port in ports:
            if not isinstance(port, dict) or len(port) > 16:
                invalid += 1
                continue
            valid_ports += 1
            unknown += sum(key not in _SWITCH_PORT_FIELDS for key in port)
            if "port" in port and (type(port["port"]) is not int or
                                    not -(2**31) <= port["port"] <= 2**31 - 1):
                invalid += 1
            if "port" in port:
                redacted += 1
            for key, output in (("dot1xEnable", "dot1x_enabled"),
                                ("mabEnable", "mab_enabled"), ("lag", "lag")):
                if key not in port:
                    unknown_port_flags += 1
                elif type(port[key]) is bool:
                    port_flags[output][str(port[key]).lower()] += 1
                else:
                    invalid += 1
                    unknown_port_flags += 1
            if "authType" not in port:
                unknown_auth_types += 1
            elif type(port["authType"]) is int and port["authType"] in (0, 1, 2, 3):
                key = str(port["authType"])
                auth_type_counts[key] = auth_type_counts.get(key, 0) + 1
            elif type(port["authType"]) is int:
                unknown_auth_types += 1
            else:
                invalid += 1
                unknown_auth_types += 1
            if "operation" in port:
                redacted += 1
                if not _valid_text(port["operation"], 128):
                    invalid += 1

    truncated_switches = len(raw) > MAX_DEVICES
    coverage_unknown = (len(raw) >= MAX_DEVICES or
                        port_coverage_unknown_switches > 0)
    return {
        "returned_switch_count": len(raw),
        "processed_switch_count": len(rows),
        "valid_switch_count": valid_switches,
        "status_category_counts": status_counts,
        "unknown_status_category_count": unknown_status,
        "device_flag_counts": device_flags,
        "unknown_device_flag_count": unknown_device_flags,
        "returned_port_count": returned_ports,
        "processed_port_count": processed_ports,
        "valid_port_count": valid_ports,
        "port_flag_counts": port_flags,
        "unknown_port_flag_count": unknown_port_flags,
        "auth_type_counts": auth_type_counts,
        "unknown_auth_type_count": unknown_auth_types,
        "truncated_switch_rows": max(0, len(raw) - MAX_DEVICES),
        "truncated_port_rows": truncated_ports,
        "port_coverage_unknown_switches": port_coverage_unknown_switches,
        "coverage_unknown": coverage_unknown,
        "truncated": bool(truncated_switches or truncated_ports),
        "redacted_field_count": redacted,
        "unknown_field_count": unknown,
        "invalid_field_count": invalid,
        "partial": bool(invalid or unknown or unknown_status or unknown_device_flags or
                         unknown_port_flags or unknown_auth_types or truncated_switches or
                         truncated_ports or coverage_unknown),
    }
