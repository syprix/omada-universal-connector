from __future__ import annotations

from collections import Counter
import re
from typing import Any


class SwitchRoutingTableError(ValueError):
    pass


MAX_ROWS = 10000
MAX_TYPES = 64
_TYPE = re.compile(r"[A-Za-z0-9 _-]{1,64}\Z")


def summarize_switch_routing_table(rows: list[Any]) -> dict[str, object]:
    """Count documented route types and numeric values without returning addresses."""
    if len(rows) > MAX_ROWS:
        raise SwitchRoutingTableError("row_limit")
    by_type: Counter[str] = Counter()
    by_distance: Counter[int] = Counter()
    by_metric: Counter[int] = Counter()
    unknown_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            unknown_rows += 1
            continue
        kind, distance, metric = row.get("type"), row.get("distance"), row.get("metric")
        valid_type = isinstance(kind, str) and _TYPE.fullmatch(kind) is not None and (
            kind in by_type or len(by_type) < MAX_TYPES)
        valid_distance = isinstance(distance, int) and not isinstance(distance, bool) and -(2**31) <= distance <= 2**31 - 1
        valid_metric = isinstance(metric, int) and not isinstance(metric, bool) and -(2**31) <= metric <= 2**31 - 1
        if valid_type:
            by_type[kind] += 1
        if valid_distance:
            by_distance[distance] += 1
        if valid_metric:
            by_metric[metric] += 1
        if not (valid_type and valid_distance and valid_metric):
            unknown_rows += 1
    return {
        "status": "ok",
        "resource": "switch_routing_table",
        "count": len(rows),
        "summary": {
            "by_type": dict(sorted(by_type.items())),
            "by_distance": dict(sorted(by_distance.items())),
            "by_metric": dict(sorted(by_metric.items())),
            "unknown_rows": unknown_rows,
        },
        "partial": unknown_rows > 0,
    }
