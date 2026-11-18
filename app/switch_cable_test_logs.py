"""Bounded projection of stored switch cable-test logs."""
from __future__ import annotations


class SwitchCableTestLogsError(ValueError):
    """Input exceeds the documented bounded log projection."""


_LISTS = {
    "testPortList": "test_ports",
    "completePortList": "complete_ports",
    "cancelPortList": "cancelled_ports",
    "timeoutPortList": "timed_out_ports",
}
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_INT64_MAX = 2**63 - 1
_MAX_LOGS = 64
_MAX_PORTS_PER_LIST = 128
_MAX_TOTAL_PORTS = 4096


def _int32(value: object) -> bool:
    return type(value) is int and _INT32_MIN <= value <= _INT32_MAX


def project_switch_cable_test_logs(raw: object) -> dict[str, object]:
    if not isinstance(raw, list) or len(raw) > _MAX_LOGS:
        raise SwitchCableTestLogsError()
    logs: list[dict[str, object]] = []
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0
    total_ports = 0
    for index, row in enumerate(raw):
        if not isinstance(row, dict) or len(row) > 32:
            omitted.add("invalid_logs")
            omitted_count += 1
            continue
        if any(not isinstance(key, str) or len(key) > 128 for key in row):
            raise SwitchCableTestLogsError()
        projected: dict[str, object] = {}
        for field in ("type", "timeStamp"):
            path = f"logs[{index}].{field}"
            if field not in row:
                missing.append(path)
                omitted_count += 1
                continue
            value = row[field]
            valid = (_int32(value) if field == "type" else
                     type(value) is int and 0 <= value <= _INT64_MAX)
            if valid:
                # Timestamp units and test-type meanings are not stated in the exports.
                projected["type_code" if field == "type" else "timestamp_value"] = value
            else:
                omitted.add(path)
                omitted_count += 1
        for source_name, output_name in _LISTS.items():
            path = f"logs[{index}].{source_name}"
            if source_name not in row:
                missing.append(path)
                omitted_count += 1
                continue
            entries = row[source_name]
            if not isinstance(entries, list):
                omitted.add(path)
                omitted_count += 1
                continue
            if len(entries) > _MAX_PORTS_PER_LIST:
                raise SwitchCableTestLogsError()
            ports: list[int] = []
            for port_index, entry in enumerate(entries):
                if not isinstance(entry, dict) or len(entry) > 8:
                    omitted.add("invalid_ports")
                    omitted_count += 1
                    continue
                port = entry.get("port")
                if _int32(port):
                    ports.append(port)
                    total_ports += 1
                    if total_ports > _MAX_TOTAL_PORTS:
                        raise SwitchCableTestLogsError()
                else:
                    omitted.add(f"{path}[{port_index}]")
                    omitted_count += 1
                if set(entry) - {"port", "standardPort"}:
                    omitted.add("unknown_fields")
                    omitted_count += len(set(entry) - {"port", "standardPort"})
                if "standardPort" in entry:
                    omitted.add("port_location_details")
                    omitted_count += 1
            projected[output_name] = ports
        extras = sum(key not in {"type", "timeStamp", *_LISTS} for key in row)
        if extras:
            omitted.add("unknown_fields")
            omitted_count += extras
        logs.append(projected)
    return {"status": "ok", "resource": "switch_cable_test_logs",
            "data": {"logs": logs}, "count": len(logs),
            "partial": bool(missing or omitted_count), "missing_fields": missing,
            "omitted_field_count": omitted_count,
            "omitted_fields": sorted(omitted)}
