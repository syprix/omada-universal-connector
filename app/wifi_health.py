"""Bounded, privacy-preserving projection for site Wi-Fi health timelines."""
from __future__ import annotations

from collections import Counter
from typing import Any


class WifiHealthProjectionError(ValueError):
    """Stable error for malformed Wi-Fi health timeline results."""


_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAX_EXAMINED = 10_000
_MAX_RETURNED = 512
_ROOT_FIELDS = frozenset({"scores"})
_POINT_FIELDS = frozenset({"time", "score"})


def project_wifi_health(response_result: object, start_ms: int, end_ms: int) -> dict[str, Any]:
    """Project documented ``scores[{time:int64,score:int32}]`` in an ms window.

    ``score`` is kept as the documented raw integer; no range, percentage,
    enum, or quality label is inferred. Unknown fields and omitted points are
    counted and make the result partial. Duplicate timestamps are ambiguous,
    so all points at that timestamp are omitted.
    """
    if (type(start_ms) is not int or type(end_ms) is not int or
            not _INT64_MIN <= start_ms <= _INT64_MAX or
            not _INT64_MIN <= end_ms <= _INT64_MAX or start_ms > end_ms):
        raise WifiHealthProjectionError("window_invalid")
    if not isinstance(response_result, dict) or "scores" not in response_result:
        raise WifiHealthProjectionError("result_invalid")
    rows = response_result["scores"]
    if not isinstance(rows, list):
        raise WifiHealthProjectionError("scores_invalid")

    examined = min(len(rows), _MAX_EXAMINED)
    counters: Counter[str] = Counter({
        "received_points": len(rows), "examined_points": examined,
        "unexamined_points": len(rows) - examined, "outside_window_points": 0,
        "duplicate_timestamp_points": 0, "truncated_points": 0,
        "returned_points": 0, "unknown_fields": 0,
    })
    if set(response_result) - _ROOT_FIELDS:
        counters["unknown_fields"] += len(set(response_result) - _ROOT_FIELDS)

    selected: dict[int, dict[str, int]] = {}
    duplicate_times: set[int] = set()
    for row in rows[:examined]:
        if not isinstance(row, dict) or not _POINT_FIELDS.issubset(row):
            raise WifiHealthProjectionError("score_invalid")
        timestamp, score = row["time"], row["score"]
        if (type(timestamp) is not int or not _INT64_MIN <= timestamp <= _INT64_MAX or
                type(score) is not int or not _INT32_MIN <= score <= _INT32_MAX):
            raise WifiHealthProjectionError("score_invalid")
        if set(row) - _POINT_FIELDS:
            counters["unknown_fields"] += len(set(row) - _POINT_FIELDS)
        if timestamp < start_ms or timestamp > end_ms:
            counters["outside_window_points"] += 1
            continue
        if timestamp in duplicate_times:
            counters["duplicate_timestamp_points"] += 1
            continue
        if timestamp in selected:
            selected.pop(timestamp)
            duplicate_times.add(timestamp)
            counters["duplicate_timestamp_points"] += 2
            continue
        selected[timestamp] = {"time_ms": timestamp, "score": score}

    ordered = [selected[key] for key in sorted(selected)]
    returned = ordered[:_MAX_RETURNED]
    counters["truncated_points"] = max(0, len(ordered) - len(returned))
    counters["returned_points"] = len(returned)
    omitted = (counters["unexamined_points"] + counters["outside_window_points"] +
               counters["duplicate_timestamp_points"] + counters["truncated_points"])
    return {
        "status": "ok",
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "scores": returned,
        "partial": bool(omitted or counters["unknown_fields"]),
        "counts": dict(counters),
    }
