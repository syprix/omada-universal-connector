"""Bounded, redacted summary of networks assigned to one switch stack."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SiteStackNetworkSummaryError(ValueError):
    """The upstream stack network response is outside the documented shape."""


def summarize_stack_networks(
    stack_ref: str,
    rows: object,
    support_ipv6_values: object,
    *,
    omitted_network_count: int = 0,
) -> dict[str, Any]:
    if (type(stack_ref) is not str or not stack_ref or len(stack_ref) > 128 or
            not isinstance(rows, list) or len(rows) > 1000 or
            not isinstance(support_ipv6_values, list) or len(support_ipv6_values) > 10 or
            type(omitted_network_count) is not int or omitted_network_count < 0):
        raise SiteStackNetworkSummaryError("input_invalid")

    mode_counts = {"none": 0, "dhcp_server": 0, "dhcp_relay": 0, "unknown": 0}
    status_counts = {"enabled": 0, "disabled": 0, "unreported": 0}
    management_counts = {"yes": 0, "no": 0, "unreported": 0}
    ipv6_enabled_counts = {"enabled": 0, "disabled": 0, "unreported": 0}
    invalid_rows = missing_fields = unknown_modes = 0
    partial = omitted_network_count > 0
    for row in rows:
        if not isinstance(row, Mapping):
            invalid_rows += 1
            partial = True
            continue
        if (type(row.get("id")) is not str or not row.get("id") or
                type(row.get("vlan")) is not int):
            invalid_rows += 1
            partial = True
            continue
        mode = row.get("mode")
        if type(mode) is int and mode in (0, 1, 2):
            mode_counts[("none", "dhcp_server", "dhcp_relay")[mode]] += 1
        else:
            mode_counts["unknown"] += 1
            unknown_modes += 1
            partial = True
        for value, counts, yes, no in (
                (row.get("status"), status_counts, "enabled", "disabled"),
                (row.get("mvlan"), management_counts, "yes", "no"),
                (row.get("ipv6Enable"), ipv6_enabled_counts, "enabled", "disabled")):
            if type(value) is bool:
                counts[yes if value else no] += 1
            else:
                counts["unreported"] += 1
                missing_fields += 1
                partial = True

    valid_support = [value for value in support_ipv6_values if type(value) is bool]
    if len(valid_support) != len(support_ipv6_values) or not valid_support:
        support_ipv6: bool | None = None
        partial = True
    elif len(set(valid_support)) != 1:
        support_ipv6 = None
        partial = True
    else:
        support_ipv6 = valid_support[0]

    return {
        "status": "partial" if partial else "ok",
        "resource": "site_stack_network_summary",
        "stack_ref": stack_ref,
        "reported_network_count": len(rows),
        "omitted_network_count": omitted_network_count,
        "dhcp_mode_counts": mode_counts,
        "enabled_state_counts": status_counts,
        "management_network_counts": management_counts,
        "ipv6_enabled_counts": ipv6_enabled_counts,
        "ipv6_supported": support_ipv6,
        "invalid_rows": invalid_rows,
        "missing_optional_fields": missing_fields,
        "unknown_dhcp_modes": unknown_modes,
        "partial": partial,
    }
