"""Count controller-reported SNMP-incompatible device rows without projecting fields."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_ROWS = 1_000


def summarize_snmp_incompatible_rows(
        rows: object, reported_total: object, omitted_rows: int) -> dict[str, Any]:
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or
            type(reported_total) is not int or reported_total < len(rows) or
            type(omitted_rows) is not int or omitted_rows < 0 or
            omitted_rows > reported_total - len(rows)):
        raise ValueError("input_invalid")
    invalid_rows = sum(not isinstance(row, Mapping) for row in rows)
    partial = omitted_rows > 0 or invalid_rows > 0
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_snmp_incompatible_summary",
        "reported_incompatible_device_total": reported_total,
        "returned_device_row_count": len(rows),
        "omitted_device_row_count": omitted_rows,
        "invalid_row_count": invalid_rows,
        "partial": partial,
        "device_fields_and_per_device_assignments_returned": False,
        "device_identities_or_status_inferred": False,
    }
