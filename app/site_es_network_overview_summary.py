"""Redacted network/port-association counts for an inventoried ES switch."""
from __future__ import annotations

from collections.abc import Mapping


class EsNetworkOverviewError(ValueError):
    pass


_FIELDS = frozenset(("id", "name", "vlan", "nativePorts", "untaggedPorts",
                     "taggedPorts"))
_PORT_FIELDS = ("nativePorts", "untaggedPorts", "taggedPorts")


def summarize_es_network_overview(value: object, *, max_items: int = 1000
                                  ) -> dict[str, object]:
    if not isinstance(value, list) or type(max_items) is not int or max_items < 1:
        raise EsNetworkOverviewError("invalid network overview")
    counts = {"native": 0, "untagged": 0, "tagged": 0}
    presence = {key: {"reported_row_count": 0, "unreported_row_count": 0}
                for key in counts}
    invalid_rows = invalid_fields = unknown_fields = 0
    rows_with_assignments = 0
    for row in value[:max_items]:
        if not isinstance(row, Mapping) or len(row) > 24:
            invalid_rows += 1
            continue
        unknown_fields += sum(key not in _FIELDS for key in row)
        row_has_assignment = False
        for source, output in zip(_PORT_FIELDS, counts):
            ports = row.get(source)
            if ports is None:
                presence[output]["unreported_row_count"] += 1
                continue
            if not isinstance(ports, list) or len(ports) > 512:
                invalid_fields += 1
                presence[output]["unreported_row_count"] += 1
                continue
            presence[output]["reported_row_count"] += 1
            for port in ports:
                if type(port) is int:
                    counts[output] += 1
                    row_has_assignment = True
                else:
                    invalid_fields += 1
        rows_with_assignments += int(row_has_assignment)
    returned = min(len(value), max_items)
    total = sum(counts.values())
    return {
        "status": "ok", "resource": "site_es_network_overview_summary",
        "reported_network_count": len(value), "returned_network_count": returned,
        "network_rows_with_port_assignments": rows_with_assignments,
        "port_assignment_counts": counts, "total_port_assignment_count": total,
        "port_array_field_coverage": presence,
        "invalid_record_count": invalid_rows, "invalid_field_count": invalid_fields,
        "unknown_field_count": unknown_fields, "truncated": len(value) > max_items,
        "partial": bool(invalid_rows or invalid_fields or unknown_fields or len(value) > max_items or
                         any(presence[key]["unreported_row_count"] for key in presence)),
    }
