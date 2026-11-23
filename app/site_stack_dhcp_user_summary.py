"""Redacted type and binding counts from one stack DHCP user grid."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


class SiteStackDhcpUserSummaryError(ValueError):
    """The DHCP user rows are outside the documented bounded shape."""


MAX_ROWS = 1_000
_FIELDS = {
    "type", "ipAddress", "macAddress", "name", "showingType", "model",
    "modelVersion", "netId", "netName", "serverName", "serverMac",
    "serverStackId", "leftLeaseTime", "status", "ipLong",
}


def summarize_stack_dhcp_user_rows(
        rows: object, omitted_rows: int = 0) -> dict[str, Any]:
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or
            type(omitted_rows) is not int or omitted_rows < 0):
        raise SiteStackDhcpUserSummaryError("input_invalid")
    types: Counter[str] = Counter()
    bindings = {"dynamic": 0, "static": 0, "unreported": 0}
    invalid_rows = unknown_fields = 0
    partial = omitted_rows > 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > len(_FIELDS):
            invalid_rows += 1
            types["unknown"] += 1
            bindings["unreported"] += 1
            partial = True
            continue
        row_unknown = sum(key not in _FIELDS for key in row)
        unknown_fields += row_unknown
        if row_unknown:
            partial = True
        user_type = row.get("type")
        if type(user_type) is int and user_type in (0, 1):
            types["device" if user_type == 0 else "client"] += 1
        else:
            types["unknown"] += 1
            partial = True
        binding = row.get("status")
        if type(binding) is int and binding in (0, 1):
            bindings["dynamic" if binding == 0 else "static"] += 1
        else:
            bindings["unreported"] += 1
            partial = True
    partial = partial or bool(invalid_rows or unknown_fields)
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_stack_dhcp_user_summary",
        "returned_user_count": len(rows),
        "omitted_user_count": omitted_rows,
        "reported_user_total": len(rows) + omitted_rows,
        "by_documented_user_type": dict(sorted(types.items())),
        "by_documented_binding_status": bindings,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "addresses_names_and_binding_rows_returned": False,
    }
