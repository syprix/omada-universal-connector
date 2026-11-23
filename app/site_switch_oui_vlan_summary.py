"""Redacted counts for switch OUI-based VLAN rules."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


class SiteSwitchOuiVlanSummaryError(ValueError):
    """The rule rows are outside the documented bounded shape."""


MAX_ROWS = 1_000
_FIELDS = {"id", "enable", "name", "mode", "deviceList", "ruleCombine"}


def summarize_switch_oui_vlan_rows(
        rows: object, omitted_rows: int = 0) -> dict[str, Any]:
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or
            type(omitted_rows) is not int or omitted_rows < 0):
        raise SiteSwitchOuiVlanSummaryError("input_invalid")
    enabled = {"true": 0, "false": 0, "unreported": 0}
    modes: Counter[str] = Counter()
    invalid_rows = unknown_fields = 0
    partial = omitted_rows > 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > len(_FIELDS):
            invalid_rows += 1
            enabled["unreported"] += 1
            modes["unknown"] += 1
            partial = True
            continue
        row_unknown = sum(key not in _FIELDS for key in row)
        unknown_fields += row_unknown
        if row_unknown:
            partial = True
        flag = row.get("enable")
        if type(flag) is bool:
            enabled["true" if flag else "false"] += 1
        else:
            enabled["unreported"] += 1
            partial = True
        mode = row.get("mode")
        if type(mode) is int and mode in (0, 1):
            modes["all_device_ports" if mode == 0 else "custom_device_ports"] += 1
        else:
            modes["unknown"] += 1
            partial = True
    partial = partial or bool(invalid_rows or unknown_fields)
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_switch_oui_vlan_summary",
        "returned_rule_count": len(rows),
        "omitted_rule_count": omitted_rows,
        "reported_rule_total": len(rows) + omitted_rows,
        "by_reported_enabled_flag": enabled,
        "by_documented_port_scope_mode": dict(sorted(modes.items())),
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "rule_ids_names_oui_and_vlan_values_returned": False,
        "enforcement_or_assignments_inferred": False,
    }
