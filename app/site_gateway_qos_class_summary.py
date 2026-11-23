"""Redacted, bounded summary of gateway QoS class rules."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_ROWS = 1000


def summarize_gateway_qos_class_rows(
    rows: object, *, source_total: int, omitted_rows: int = 0,
) -> dict[str, Any]:
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or type(source_total) is not int or
            source_total < len(rows) or type(omitted_rows) is not int or
            omitted_rows < 0 or omitted_rows > source_total - len(rows)):
        raise ValueError("invalid gateway QoS class grid")

    enabled = {"enabled": 0, "disabled": 0, "unknown": 0, "missing": 0}
    ip_versions = {"0": 0, "1": 0, "unknown": 0, "missing": 0}
    classes = {"1": 0, "2": 0, "3": 0, "unknown": 0, "missing": 0}
    invalid_rows = 0

    for row in rows:
        if not isinstance(row, Mapping):
            invalid_rows += 1
            enabled["unknown"] += 1
            ip_versions["unknown"] += 1
            classes["unknown"] += 1
            continue

        value = row.get("enable")
        if "enable" not in row:
            enabled["missing"] += 1
        elif type(value) is not bool:
            enabled["unknown"] += 1
        else:
            enabled["enabled" if value else "disabled"] += 1

        value = row.get("ipVersion")
        if "ipVersion" not in row:
            ip_versions["missing"] += 1
        elif type(value) is not int or value not in (0, 1):
            ip_versions["unknown"] += 1
        else:
            ip_versions[str(value)] += 1

        value = row.get("classType")
        if "classType" not in row:
            classes["missing"] += 1
        elif type(value) is not int or value not in (1, 2, 3):
            classes["unknown"] += 1
        else:
            classes[str(value)] += 1

    omitted = omitted_rows
    return {
        "summarized_rule_count": len(rows),
        "source_total_rule_count": source_total,
        "omitted_rule_count": omitted,
        "enabled_state_counts": enabled,
        "documented_ip_version_counts": ip_versions,
        "documented_class_counts": classes,
        "invalid_row_count": invalid_rows,
        "partial": bool(omitted or invalid_rows or enabled["unknown"] or enabled["missing"] or
                         ip_versions["unknown"] or ip_versions["missing"] or
                         classes["unknown"] or classes["missing"]),
        "traffic_state": "configuration only",
    }
