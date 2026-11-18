"""Redacted per-network DHCP pool availability and lease counts."""
from __future__ import annotations

import ipaddress
from collections import Counter
from collections.abc import Mapping, Sequence

MAX_RANGES = 64
MAX_LEASES = 20_000
MAX_FIELDS = 16


class DhcpPoolUtilizationError(ValueError):
    """The DHCP pool or lease data is incomplete or outside safe bounds."""


def _ipv4(value: object) -> int | None:
    if not isinstance(value, str) or len(value) > 15:
        return None
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return None
    return int(parsed) if parsed.version == 4 and str(parsed) == value else None


def _lease_counts(leases: Sequence[object], expected_network_id: str
                  ) -> tuple[Counter[str], int]:
    if len(leases) > MAX_LEASES:
        raise DhcpPoolUtilizationError("lease_count_limit")
    counts: Counter[str] = Counter()
    invalid = 0
    for row in leases:
        if not isinstance(row, Mapping) or len(row) > MAX_FIELDS:
            invalid += 1
            continue
        network_id = row.get("netId")
        if network_id != expected_network_id:
            continue
        binding = row.get("status")
        entity_type = row.get("type")
        if type(binding) is not int or binding not in (0, 1) or type(entity_type) is not int or entity_type not in (0, 1):
            invalid += 1
            counts["invalid"] += 1
            continue
        counts["dynamic" if binding == 0 else "static"] += 1
    return counts, invalid


def project_dhcp_pool_utilization(result: object, leases: Sequence[object],
                                  network_id: str) -> dict[str, object]:
    """Count capacity and available addresses without returning pool boundaries."""
    if not isinstance(result, Mapping) or len(result) > MAX_FIELDS:
        raise DhcpPoolUtilizationError("pool_result_invalid")
    raw_ranges = result.get("ranges")
    if not isinstance(raw_ranges, list) or len(raw_ranges) > MAX_RANGES:
        raise DhcpPoolUtilizationError("pool_ranges_invalid")
    if not isinstance(network_id, str) or not network_id or len(network_id) > 128:
        raise DhcpPoolUtilizationError("network_id_invalid")

    range_capacity = 0
    available_total = 0
    missing = invalid = unknown = 0
    intervals: list[tuple[int, int]] = []
    all_capacity_known = all_available_known = True
    for row in raw_ranges:
        if not isinstance(row, Mapping) or len(row) > MAX_FIELDS:
            invalid += 1
            all_capacity_known = all_available_known = False
            continue
        unknown += sum(key not in {"startIp", "endIp", "availableIpNum"} for key in row)
        start, end = _ipv4(row.get("startIp")), _ipv4(row.get("endIp"))
        if start is None or end is None or end < start:
            invalid += 1
            all_capacity_known = False
        else:
            intervals.append((start, end))
            range_capacity += end - start + 1
        available = row.get("availableIpNum")
        if type(available) is int and 0 <= available <= 2_147_483_647:
            available_total += available
        else:
            if "availableIpNum" not in row:
                missing += 1
            else:
                invalid += 1
            all_available_known = False
    intervals.sort()
    overlap_count = 0
    max_end: int | None = None
    for start, end in intervals:
        if max_end is not None and start <= max_end:
            overlap_count += 1
        max_end = end if max_end is None else max(max_end, end)
    if overlap_count:
        invalid += overlap_count
        all_capacity_known = False

    lease, invalid_lease_count = _lease_counts(leases, network_id)
    configured = len(raw_ranges) > 0
    capacity = range_capacity if configured and all_capacity_known else None
    available = available_total if configured and all_available_known else None
    inconsistent = (type(capacity) is int and type(available) is int and available > capacity)
    if inconsistent:
        available = None
        invalid += 1
    depleted = (available == 0 and type(capacity) is int and capacity > 0)
    return {
        "data": {
            "pool_state": ("no_configured_ranges" if not configured else
                           "complete" if capacity is not None and available is not None else
                           "incomplete"),
            "range_count": len(raw_ranges),
            "pool_capacity_address_count": capacity,
            "available_address_count": available,
            "non_available_address_count": (capacity - available
                                             if capacity is not None and available is not None
                                             else None),
            "availability_percent": (round(available * 100 / capacity, 2)
                                     if capacity and available is not None else None),
            "pool_exhausted": depleted if capacity is not None and available is not None else None,
            "lease_count": lease.get("dynamic", 0) + lease.get("static", 0),
            "dynamic_lease_count": lease.get("dynamic", 0),
            "static_lease_count": lease.get("static", 0),
            "unclassified_lease_count": lease.get("invalid", 0),
            "lease_pool_membership": "not_returned_by_source",
            "invalid_network_lease_count": invalid_lease_count,
            "overlapping_range_count": overlap_count,
            "missing_pool_value_count": missing,
            "invalid_pool_value_count": invalid,
            "unknown_pool_field_count": unknown,
        },
        "partial": bool(invalid or unknown or missing or invalid_lease_count),
    }
