"""Redacted status for one history selected by a site-scoped opaque reference."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SiteBatchInterferenceStatusSummaryError(ValueError):
    """The status response does not match its documented bounded shape."""


def summarize_site_batch_interference_status(
        value: Any, *, expected_history_id: str) -> dict[str, object]:
    if not isinstance(expected_history_id, str) or not expected_history_id:
        raise SiteBatchInterferenceStatusSummaryError("expected_id_invalid")
    if not isinstance(value, list) or len(value) > 10:
        raise SiteBatchInterferenceStatusSummaryError("result_invalid")
    result: list[dict[str, object]] = []
    invalid = unknown = 0
    for row in value:
        if not isinstance(row, Mapping):
            invalid += 1
            continue
        unknown += sum(key not in {"historyId", "status"} for key in row)
        history_id = row.get("historyId")
        status = row.get("status")
        if history_id != expected_history_id:
            invalid += 1
            continue
        if type(status) is not int or status not in (0, 1):
            invalid += 1
            continue
        result.append({"status": "finished" if status == 0 else "scanning"})
    if len(result) != 1:
        invalid += 1
        result = []
    return {"data": {"result_count": len(result), "items": result,
                     "invalid_value_count": invalid,
                     "unknown_field_count": unknown},
            "partial": bool(invalid or unknown)}
