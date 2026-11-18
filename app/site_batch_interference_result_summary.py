"""Bounded counters for the recursive batch interference response schema."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SiteBatchInterferenceResultSummaryError(ValueError):
    """The batch interference response exceeds its supported shape."""


_BANDS = (("interferences2g", "2g"), ("interferences5g", "5g"),
          ("interferences6g", "6g"))
_BAND_FIELDS = frozenset(key for key, _label in _BANDS)
_MAX_ROWS = 100
_MAX_ARRAY = 256
_MAX_OBJECTS = 2_048
_MAX_DEPTH = 8


def summarize_site_batch_interferences(value: Any) -> dict[str, object]:
    """Count documented nested band entries without returning source records."""
    if not isinstance(value, list) or len(value) > _MAX_ROWS:
        raise SiteBatchInterferenceResultSummaryError("result_invalid")
    counts = {label: 0 for _key, label in _BANDS}
    visited = 0
    omitted = 0
    unknown = 0
    partial = False

    def visit(node: object, depth: int) -> None:
        nonlocal visited, omitted, unknown, partial
        if not isinstance(node, Mapping):
            omitted += 1
            partial = True
            return
        visited += 1
        if visited > _MAX_OBJECTS:
            raise SiteBatchInterferenceResultSummaryError("object_limit")
        extra = sum(key not in _BAND_FIELDS for key in node)
        unknown += extra
        partial = partial or bool(extra)
        for field, label in _BANDS:
            if field not in node or node[field] is None:
                partial = True
                continue
            entries = node[field]
            if not isinstance(entries, list) or len(entries) > _MAX_ARRAY:
                raise SiteBatchInterferenceResultSummaryError("band_list_invalid")
            counts[label] += len(entries)
            if depth >= _MAX_DEPTH and entries:
                omitted += len(entries)
                partial = True
                continue
            for child in entries:
                visit(child, depth + 1)

    for row in value:
        visit(row, 0)
    return {"data": {"band_entry_counts": counts,
                     "returned_result_count": len(value),
                     "visited_object_count": visited,
                     "omitted_value_count": omitted,
                     "unknown_field_count": unknown,
                     "page": 1, "page_size": _MAX_ROWS,
                     "coverage_scope": "first_page_only",
                     "coverage_unknown": True},
            "partial": True}
