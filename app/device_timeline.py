"""Aggregate online intervals without exposing exact device event times."""
from __future__ import annotations

from typing import Any

MAX_INTERVALS = 500
MAX_I64 = 2**63 - 1
FIELDS = {"start", "end", "duration"}


class DeviceTimelineError(ValueError):
    """Raised when the device timeline exceeds its structural bounds."""


def project_device_timeline(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise DeviceTimelineError("response_invalid")
    if "connections" not in result:
        return {"data": {"interval_count": None, "online_duration_ms": None,
                         "missing_duration_count": 0, "invalid_count": 0,
                         "unknown_field_count": len(result.keys() - {"connections"})},
                "partial": True}
    rows = result["connections"]
    if not isinstance(rows, list) or len(rows) > MAX_INTERVALS:
        raise DeviceTimelineError("response_invalid")
    total_duration = 0
    missing_duration = invalid = 0
    unknown = len(result.keys() - {"connections"})
    for row in rows:
        if not isinstance(row, dict) or len(row) > 16:
            raise DeviceTimelineError("response_invalid")
        unknown += len(row.keys() - FIELDS)
        for field in ("start", "end"):
            if field in row and (type(row[field]) is not int or not 0 <= row[field] <= MAX_I64):
                invalid += 1
        if "duration" not in row:
            missing_duration += 1
        else:
            duration = row["duration"]
            if type(duration) is not int or not 0 <= duration <= MAX_I64:
                invalid += 1
            else:
                total_duration += duration
                if total_duration > MAX_I64:
                    invalid += 1
                    total_duration -= duration
    complete = missing_duration == 0 and invalid == 0 and unknown == 0
    return {
        "data": {"interval_count": len(rows),
                 "online_duration_ms": total_duration if complete else None,
                 "missing_duration_count": missing_duration,
                 "invalid_count": invalid, "unknown_field_count": unknown},
        "partial": not complete,
    }
