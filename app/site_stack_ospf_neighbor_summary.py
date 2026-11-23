"""Redacted row coverage for one stack's documented OSPF neighbor grid."""
from __future__ import annotations

from collections.abc import Mapping


class StackOspfNeighborSummaryError(ValueError):
    pass


def summarize_stack_ospf_neighbors(rows: object, total_rows: object,
                                  omitted_rows: object) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 1_000 or
            type(total_rows) is not int or not len(rows) <= total_rows < (1 << 63) or
            type(omitted_rows) is not int or omitted_rows != total_rows - len(rows)):
        raise StackOspfNeighborSummaryError("input_invalid")

    state_reported = invalid_rows = invalid_state_fields = 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 16:
            invalid_rows += 1
            continue
        state = row.get("state")
        if isinstance(state, str):
            state_reported += 1
        elif state is not None:
            invalid_state_fields += 1

    return {
        "neighbor_row_count": len(rows),
        "reported_total_count": total_rows,
        "omitted_row_count": omitted_rows,
        "coverage_complete": omitted_rows == 0,
        "state_field_reported_count": state_reported,
        "invalid_record_count": invalid_rows,
        "invalid_state_field_count": invalid_state_fields,
        "partial": bool(omitted_rows or invalid_rows or invalid_state_fields),
        "state_values_interpreted": False,
        "neighbor_addresses_router_ids_interfaces_and_process_ids_returned": False,
    }
