"""Redacted inventory counts for adopted and pending bridge devices."""
from __future__ import annotations

from collections import Counter
from typing import Any


class SiteBridgeDeviceSummaryError(ValueError):
    pass


MAX_ROWS = 10_000


def summarize_site_bridge_devices(
        adopted: dict[str, Any], pending: dict[str, Any]) -> dict[str, object]:
    adopted_summary = _summarize_grid(adopted, include_stacks=True)
    pending_summary = _summarize_grid(pending, include_stacks=False)
    return {
        "status": "ok", "resource": "site_bridge_device_summary",
        "adopted": adopted_summary,
        "pending": pending_summary,
        "partial": bool(adopted_summary["partial"] or pending_summary["partial"]),
        "identifiers_returned": False,
        "scope": "documented adopted/pending bridge-device grid reads only",
    }


def _summarize_grid(result: dict[str, Any], *, include_stacks: bool) -> dict[str, object]:
    rows = result.get("data")
    total = result.get("totalRows")
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or
            not isinstance(total, int) or isinstance(total, bool) or total < len(rows)):
        raise SiteBridgeDeviceSummaryError("grid_invalid")
    statuses: Counter[str] = Counter()
    details: Counter[str] = Counter()
    invalid = 0
    for row in rows:
        if not isinstance(row, dict):
            invalid += 1
            continue
        status = row.get("status")
        detail = row.get("detailStatus")
        statuses[str(status) if isinstance(status, int) and not isinstance(status, bool)
                 else "unknown"] += 1
        details[str(detail) if isinstance(detail, int) and not isinstance(detail, bool)
                else "unknown"] += 1
    stacks = result.get("stackData") if include_stacks else None
    stack_summary: dict[str, object] | None = None
    if include_stacks:
        if not isinstance(stacks, list) or len(stacks) > MAX_ROWS:
            invalid += 1
            stack_summary = {"group_count": None, "by_status_code": {}}
        else:
            stack_status: Counter[str] = Counter()
            for stack in stacks:
                if not isinstance(stack, dict):
                    invalid += 1
                    continue
                value = stack.get("stackStatus")
                stack_status[str(value) if isinstance(value, int) and not isinstance(value, bool)
                             else "unknown"] += 1
            stack_summary = {"group_count": len(stacks),
                             "by_status_code": dict(sorted(stack_status.items()))}
    return {
        "source_total_rows": total, "returned_rows": len(rows),
        "coverage_complete": total == len(rows),
        "by_source_status_code": dict(sorted(statuses.items())),
        "by_source_detail_status_code": dict(sorted(details.items())),
        "stack_groups": stack_summary, "invalid_row_count": invalid,
        "partial": bool(invalid or total != len(rows)),
    }
