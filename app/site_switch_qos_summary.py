"""Redacted switch QoS rule counts."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_ROWS = 1_000


def summarize_switch_qos_rules(
        rows: object, total_rows: object, omitted_rows: int) -> dict[str, Any]:
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or
            type(total_rows) is not int or total_rows < len(rows) or
            type(omitted_rows) is not int or omitted_rows < 0 or
            omitted_rows > total_rows - len(rows)):
        raise ValueError("input_invalid")
    rule_type = {"network": 0, "port": 0, "custom": 0, "unknown": 0, "missing": 0}
    status = {"enabled": 0, "disabled": 0, "unknown": 0, "missing": 0}
    queues = {str(value): 0 for value in range(8)}
    queues.update({"unknown": 0, "missing": 0, "invalid": 0})
    invalid_rows = unknown_fields = 0
    known_fields = {"id", "index", "name", "status", "type", "ipVersion",
                    "lanNetworkEntries", "protocol", "dscp", "queue", "dscpEnable",
                    "dscpReEnable", "dscpRe", "bindType", "deviceList", "sPort",
                    "dPort", "macPortIdsMap", "macLagIdsMap", "macStdPortIdsMap"}
    partial = omitted_rows > 0
    for row in rows:
        if not isinstance(row, Mapping):
            invalid_rows += 1
            rule_type["unknown"] += 1
            status["unknown"] += 1
            queues["unknown"] += 1
            partial = True
            continue
        unknown_fields += sum(field not in known_fields for field in row)
        kind = row.get("type")
        if type(kind) is int and 0 <= kind <= 2:
            rule_type[("network", "port", "custom")[kind]] += 1
        elif "type" not in row:
            rule_type["missing"] += 1
        else:
            rule_type["unknown"] += 1
        enabled = row.get("status")
        if type(enabled) is bool:
            status["enabled" if enabled else "disabled"] += 1
        elif "status" not in row:
            status["missing"] += 1
        else:
            status["unknown"] += 1
        queue = row.get("queue")
        if type(queue) is int and 0 <= queue <= 7:
            queues[str(queue)] += 1
        elif "queue" not in row:
            queues["missing"] += 1
        elif type(queue) is int:
            queues["invalid"] += 1
        else:
            queues["unknown"] += 1
    partial = partial or bool(invalid_rows or unknown_fields or rule_type["unknown"] or
                              rule_type["missing"] or status["unknown"] or
                              status["missing"] or queues["unknown"] or queues["missing"] or
                              queues["invalid"])
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_switch_qos_summary",
        "reported_rule_total": total_rows,
        "returned_rule_count": len(rows),
        "omitted_rule_count": omitted_rows,
        "by_documented_rule_type": rule_type,
        "reported_rule_status": status,
        "by_documented_queue": queues,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "rule_names_ids_addresses_ports_and_other_values_returned": False,
        "traffic_behavior_inferred": False,
    }
