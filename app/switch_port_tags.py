from __future__ import annotations

from collections import Counter
from typing import Any


class SwitchPortTagsError(ValueError):
    pass


MAX_ROWS = 4096
_RESOURCE_CODES = {0, 1, 2}


def summarize_switch_port_tags(rows: list[Any]) -> dict[str, object]:
    """Count port labels and their documented source codes without label data."""
    if len(rows) > MAX_ROWS:
        raise SwitchPortTagsError("row_limit")
    resources: Counter[int] = Counter()
    unknown_rows = 0
    for row in rows:
        value = row.get("resource") if isinstance(row, dict) else None
        if type(value) is int and value in _RESOURCE_CODES:
            resources[value] += 1
        else:
            unknown_rows += 1
    return {
        "status": "ok",
        "resource": "switch_port_tags",
        "count": len(rows),
        "summary": {
            "by_resource_code": dict(sorted(resources.items())),
            "unknown_rows": unknown_rows,
        },
        "partial": unknown_rows > 0,
    }
