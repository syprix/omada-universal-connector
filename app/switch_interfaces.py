from __future__ import annotations

from collections import Counter
from typing import Any


class SwitchInterfacesError(ValueError):
    pass


MAX_ROWS = 4096


def summarize_switch_interfaces(rows: list[Any]) -> dict[str, object]:
    """Count documented interface types without returning interface names or IDs."""
    if len(rows) > MAX_ROWS:
        raise SwitchInterfacesError("row_limit")
    counts: Counter[int] = Counter()
    unknown_rows = 0
    for row in rows:
        kind = row.get("type") if isinstance(row, dict) else None
        if isinstance(kind, int) and not isinstance(kind, bool) and kind in {0, 1}:
            counts[kind] += 1
        else:
            unknown_rows += 1
    return {
        "status": "ok",
        "resource": "switch_interfaces",
        "count": len(rows),
        "summary": {"by_type_code": dict(sorted(counts.items())), "unknown_rows": unknown_rows},
        "partial": unknown_rows > 0,
    }
