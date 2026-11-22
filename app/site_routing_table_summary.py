"""Redacted page coverage for the gateway or switch routing table."""
from __future__ import annotations

from typing import Any


class SiteRoutingTableError(ValueError):
    """Malformed routing table query or page."""


_DEVICE_TYPES = {"gateway", "switch"}
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1


def project_site_routing_table(result: Any, device_type: str, page_number: int,
                               page_size: int) -> dict[str, object]:
    if (not isinstance(device_type, str) or device_type not in _DEVICE_TYPES or
            type(page_number) is not int or not 0 <= page_number <= 10_000 or
            type(page_size) is not int or not 1 <= page_size <= 100):
        raise SiteRoutingTableError("request_invalid")
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteRoutingTableError("response_invalid")
    rows, total, current, size = (result.get(k) for k in
                                  ("data", "totalRows", "currentPage", "currentSize"))
    source_page = page_number + 1
    if (not isinstance(rows, list) or len(rows) > page_size or
            type(total) is not int or total < 0 or type(current) is not int or
            current != source_page or type(size) is not int or not len(rows) <= size <= page_size):
        raise SiteRoutingTableError("response_invalid")
    type_value_rows = type_missing_rows = distance_rows = metric_rows = 0
    distinct_type_values: set[str] = set()
    invalid = unknown = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 24:
            invalid += 1
            continue
        unknown += len(set(row) - {"mac", "name", "distance", "destinationIp", "destIpVrf",
                                   "oswDestinationIps", "nextHops", "nextHop", "nextHopVrf",
                                   "nextHopsVrf", "interfaceName", "metric", "type", "stackMsg"})
        route_type = row.get("type")
        if isinstance(route_type, str) and route_type:
            type_value_rows += 1
            distinct_type_values.add(route_type)
        else:
            type_missing_rows += 1
        if "distance" in row:
            value = row["distance"]
            if type(value) is int and 0 <= value <= _INT32_MAX:
                distance_rows += 1
            else:
                invalid += 1
        if "metric" in row:
            value = row["metric"]
            if type(value) is int and 0 <= value <= _INT32_MAX:
                metric_rows += 1
            else:
                invalid += 1

    has_more = total > page_number * page_size + len(rows)
    return {
        "device_type": device_type,
        "page_number": page_number,
        "page_size": page_size,
        "reported_route_count": total,
        "sampled_route_count": len(rows),
        "has_more": has_more,
        "rows_with_documented_type_value": type_value_rows,
        "rows_with_missing_or_invalid_type": type_missing_rows,
        "distinct_uninterpreted_type_value_count": len(distinct_type_values),
        "rows_with_distance": distance_rows,
        "rows_with_metric": metric_rows,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(has_more or invalid or unknown or type_missing_rows or
                         len(rows) < min(total, page_size)),
        "destinations_and_hops_returned": False,
        "type_values_interpreted": False,
    }
