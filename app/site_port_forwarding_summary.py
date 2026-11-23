"""Redacted counts for a site's configured port-forwarding rows."""
from __future__ import annotations

from collections.abc import Mapping


class PortForwardingSummaryError(ValueError):
    pass


_FIELDS = frozenset(("id", "site id", "name", "status", "from", "limitedAddresses",
                     "interfaceWanPortId", "virtualWanId", "wanIps", "externalPort",
                     "forwardIp", "forwardPort", "protocol", "existWanIp",
                     "existVirtualWan", "featureDescription", "dMZ"))


def summarize_port_forwarding_rows(rows: object, total_rows: object,
                                   omitted_rows: object) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 1_000 or
            type(total_rows) is not int or not len(rows) <= total_rows < (1 << 63) or
            type(omitted_rows) is not int or omitted_rows != total_rows - len(rows)):
        raise PortForwardingSummaryError("input_invalid")

    status_counts = {"enabled": 0, "disabled": 0, "unknown": 0}
    protocol_counts = {"all": 0, "tcp": 0, "udp": 0, "unknown": 0}
    source_counts = {"code_0": 0, "limited_address": 0, "unknown": 0}
    invalid_rows = invalid_fields = unknown_fields = 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 32:
            invalid_rows += 1
            continue
        unknown_fields += sum(key not in _FIELDS for key in row)

        status = row.get("status")
        if type(status) is bool:
            status_counts["enabled" if status else "disabled"] += 1
        elif status is None:
            status_counts["unknown"] += 1
        else:
            invalid_fields += 1
            status_counts["unknown"] += 1

        protocol = row.get("protocol")
        if type(protocol) is int and 0 <= protocol <= 2:
            protocol_counts[{0: "all", 1: "tcp", 2: "udp"}[protocol]] += 1
        elif protocol is None:
            protocol_counts["unknown"] += 1
        else:
            invalid_fields += 1
            protocol_counts["unknown"] += 1

        source = row.get("from")
        if type(source) is int and source == 0:
            source_counts["code_0"] += 1
        elif type(source) is int and source == 1:
            source_counts["limited_address"] += 1
        elif source is None:
            source_counts["unknown"] += 1
        else:
            invalid_fields += 1
            source_counts["unknown"] += 1

    return {
        "rule_count": len(rows),
        "reported_total_count": total_rows,
        "omitted_rule_count": omitted_rows,
        "coverage_complete": omitted_rows == 0,
        "status_counts": status_counts,
        "protocol_counts": protocol_counts,
        "source_counts": source_counts,
        "invalid_record_count": invalid_rows,
        "invalid_field_count": invalid_fields,
        "unknown_field_count": unknown_fields,
        "partial": bool(omitted_rows or invalid_rows or invalid_fields or
                         unknown_fields or status_counts["unknown"] or
                         protocol_counts["unknown"] or source_counts["unknown"]),
        "addresses_ports_wan_references_and_rule_names_returned": False,
        "traffic_reachability_and_runtime_statistics_inferred": False,
    }
