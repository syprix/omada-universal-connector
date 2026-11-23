"""Redacted counts for documented static-route rows on one stack."""
from __future__ import annotations

from collections.abc import Mapping


class StackStaticRoutingSummaryError(ValueError):
    pass


def summarize_stack_static_routes(rows: object, total_rows: object,
                                  omitted_rows: object) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 1_000 or
            type(total_rows) is not int or not len(rows) <= total_rows < (1 << 63) or
            type(omitted_rows) is not int or omitted_rows != total_rows - len(rows)):
        raise StackStaticRoutingSummaryError("input_invalid")

    versions = {"ipv4": 0, "ipv6": 0, "unknown": 0}
    enabled = disabled = unknown_status = invalid_rows = invalid_fields = 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 24:
            invalid_rows += 1
            continue
        version = row.get("ipVersion")
        if version == 0 and type(version) is int:
            versions["ipv4"] += 1
        elif version == 1 and type(version) is int:
            versions["ipv6"] += 1
        elif version is None:
            versions["unknown"] += 1
        else:
            invalid_fields += 1
            versions["unknown"] += 1

        status = row.get("status")
        if type(status) is bool:
            enabled += status
            disabled += not status
        elif status is None:
            unknown_status += 1
        else:
            invalid_fields += 1
            unknown_status += 1

    return {
        "route_count": len(rows),
        "reported_total_count": total_rows,
        "omitted_route_count": omitted_rows,
        "coverage_complete": omitted_rows == 0,
        "ip_version_counts": versions,
        "enabled_count": enabled,
        "disabled_count": disabled,
        "unknown_status_count": unknown_status,
        "invalid_record_count": invalid_rows,
        "invalid_field_count": invalid_fields,
        "partial": bool(omitted_rows or invalid_rows or invalid_fields or versions["unknown"] or unknown_status),
        "active_forwarding_inferred": False,
        "route_targets_and_identifiers_returned": False,
    }
