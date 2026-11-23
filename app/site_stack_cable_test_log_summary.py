"""Redacted counts from stored switch-stack cable-test log events."""
from __future__ import annotations


class StackCableTestLogSummaryError(ValueError):
    pass


_LOG_LIMIT = 64
_PORT_LIMIT = 128
_LIST_FIELDS = ("testPortList", "completePortList", "cancelPortList", "timeoutPortList")


def summarize_stack_cable_test_logs(raw: object) -> dict[str, object]:
    if not isinstance(raw, list) or len(raw) > _LOG_LIMIT:
        raise StackCableTestLogSummaryError("logs_invalid")
    counts = {"tested_port_entries": 0, "completed_port_entries": 0,
              "cancelled_port_entries": 0, "timed_out_port_entries": 0}
    names = dict(zip(_LIST_FIELDS, counts))
    missing: list[str] = []
    omitted = 0
    log_types = {"start": 0, "completed": 0, "interrupted": 0, "timed_out": 0, "unknown": 0}
    for index, row in enumerate(raw):
        if not isinstance(row, dict) or set(row) - {"type", "timeStamp", *_LIST_FIELDS}:
            raise StackCableTestLogSummaryError("log_invalid")
        timestamp = row.get("timeStamp")
        if "timeStamp" in row and (type(timestamp) is not int or
                                     not 0 <= timestamp <= (2**63 - 1)):
            omitted += 1
        log_type = row.get("type")
        if type(log_type) is int and log_type in (0, 1, 2, 3):
            log_types[{0: "start", 1: "completed", 2: "interrupted", 3: "timed_out"}[log_type]] += 1
        elif type(log_type) is int and -(2**31) <= log_type < 2**31:
            log_types["unknown"] += 1
            omitted += 1
        else:
            missing.append(f"logs[{index}].type")
            omitted += 1
        for field in _LIST_FIELDS:
            if field not in row:
                missing.append(f"logs[{index}].{field}")
                omitted += 1
                continue
            entries = row[field]
            if not isinstance(entries, list) or len(entries) > _PORT_LIMIT:
                raise StackCableTestLogSummaryError("port_list_invalid")
            # Count entries only. Port identifiers and standard locations are never projected.
            counts[names[field]] += len(entries)
            for entry in entries:
                if not isinstance(entry, dict):
                    omitted += 1
                    continue
                if set(entry) - {"port", "standardPort"}:
                    omitted += 1
                port = entry.get("port")
                if type(port) is not int or not -(2**31) <= port < 2**31:
                    omitted += 1
    return {"log_count": len(raw), "log_type_counts": log_types,
            "port_entry_counts": counts, "partial": bool(missing or omitted),
            "missing_fields": missing, "omitted_field_count": omitted,
            "timestamps_returned": False, "port_identifiers_returned": False}
