"""Bounded, redacted switch port list used by the cable-test UI."""
from __future__ import annotations


class SwitchCableTestPortsError(ValueError):
    """Input exceeds the documented bounded port projection."""


_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAX_PORTS = 512
_MAX_REASONS = 16
_PORT_TYPES = {1, 2, 3}
_REASON_CODES = {-1, -2, -3, -4, -5}


def project_switch_cable_test_ports(raw: object) -> dict[str, object]:
    if not isinstance(raw, list) or len(raw) > _MAX_PORTS:
        raise SwitchCableTestPortsError()
    ports: list[dict[str, object]] = []
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0
    fields = ("type", "editEnable", "isUpperPort", "isDisabled", "isStackPort", "isCopper")
    for index, row in enumerate(raw):
        if not isinstance(row, dict) or len(row) > 32 or any(
                not isinstance(key, str) or len(key) > 128 for key in row):
            omitted.add("invalid_ports")
            omitted_count += 1
            continue
        item: dict[str, object] = {}
        port = row.get("port")
        if type(port) is int and _INT32_MIN <= port <= _INT32_MAX:
            item["port"] = port
        else:
            if "port" not in row:
                missing.append(f"ports[{index}].port")
            else:
                omitted.add(f"ports[{index}].port")
            omitted_count += 1
        for field in fields:
            path = f"ports[{index}].{field}"
            if field not in row:
                missing.append(path)
                omitted_count += 1
                continue
            value = row[field]
            valid = (type(value) is bool if field in {"editEnable", "isUpperPort", "isDisabled", "isStackPort", "isCopper"}
                     else type(value) is int and _INT32_MIN <= value <= _INT32_MAX and
                     (field != "type" or value in _PORT_TYPES))
            if valid:
                output_name = {
                    "type": "type_code", "isUpperPort": "upper_port",
                    "isDisabled": "disabled", "isStackPort": "stack_port",
                    "isCopper": "copper",
                }.get(field, field)
                item[output_name] = value
            else:
                omitted.add(path)
                omitted_count += 1
        reasons = row.get("reasons")
        if "reasons" not in row:
            missing.append(f"ports[{index}].reasons")
            omitted_count += 1
        elif not isinstance(reasons, list):
            omitted.add(f"ports[{index}].reasons")
            omitted_count += 1
        else:
            if len(reasons) > _MAX_REASONS:
                raise SwitchCableTestPortsError()
            item["reason_codes"] = [value for value in reasons
                                    if type(value) is int and value in _REASON_CODES]
            omitted_count += len(reasons) - len(item["reason_codes"])
            if len(item["reason_codes"]) != len(reasons):
                omitted.add(f"ports[{index}].reasons")
        extras = sum(key not in {"port", "standardPort", "type", "name", "editEnable",
                                "isUpperPort", "isDisabled", "isStackPort", "reasons",
                                "downlinkDevices", "isCopper"} for key in row)
        if extras:
            omitted.add("unknown_fields")
            omitted_count += extras
        if any(key in row for key in ("standardPort", "name", "downlinkDevices")):
            omitted.add("port_details")
            omitted_count += sum(key in row for key in ("standardPort", "name", "downlinkDevices"))
        ports.append(item)
    return {"status": "ok", "resource": "switch_cable_test_ports",
            "data": {"ports": ports}, "count": len(ports),
            "partial": bool(missing or omitted_count), "missing_fields": missing,
            "omitted_field_count": omitted_count, "omitted_fields": sorted(omitted)}
