"""Count AP group assignment and SSID override coverage without device data."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def summarize_ap_group_assignments(rows: object) -> dict[str, Any]:
    if not isinstance(rows, list) or len(rows) > 10_000:
        raise ValueError("input_invalid")
    assigned = unassigned = assignment_unknown = 0
    override_rows = override_total = override_known = override_missing = 0
    malformed = 0
    for row in rows:
        if not isinstance(row, Mapping):
            malformed += 1
            continue
        group_id = row.get("apGroupId")
        if group_id is None or group_id == "":
            unassigned += 1
        elif isinstance(group_id, str):
            assigned += 1
        else:
            assignment_unknown += 1

        if "overrideNum" not in row or row.get("overrideNum") is None:
            override_missing += 1
        else:
            value = row.get("overrideNum")
            if type(value) is int and 0 <= value <= 2**31 - 1:
                override_known += 1
                override_total += value
                override_rows += value > 0
            else:
                malformed += 1

    partial = bool(assignment_unknown or malformed or override_missing)
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_ap_group_assignment_summary",
        "ap_rows": len(rows),
        "with_reported_group_assignment": assigned,
        "without_reported_group_assignment": unassigned,
        "group_assignment_unknown": assignment_unknown,
        "rows_with_ssid_overrides": override_rows,
        "reported_ssid_override_total": override_total if override_missing == 0 and malformed == 0 else None,
        "override_value_known_rows": override_known,
        "override_value_missing_rows": override_missing,
        "malformed_rows_or_values": malformed,
        "partial": partial,
    }
