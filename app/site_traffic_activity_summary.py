"""Compact redacted summaries of AP and switch traffic samples."""
from __future__ import annotations

import math
from typing import Any


class SiteTrafficActivitySummaryError(ValueError):
    """Raised when the dashboard traffic response is malformed or oversized."""


_NETWORKS = {
    "apTrafficActivities": "access_point",
    "switchTrafficActivities": "switch",
}
_NETWORK_FIELDS = set(_NETWORKS)
_SAMPLE_FIELDS = {"time", "txData", "rxData"}
_MAX_SAMPLES_PER_NETWORK = 2_000
_INT64_MAX = (1 << 63) - 1


def _summarize_samples(samples: Any) -> tuple[dict[str, object], int, int, int, bool]:
    if not isinstance(samples, list) or len(samples) > _MAX_SAMPLES_PER_NETWORK:
        raise SiteTrafficActivitySummaryError("response_invalid")
    values: dict[str, list[float]] = {"txData": [], "rxData": []}
    timestamps: list[int] = []
    missing = invalid = unknown = 0
    complete = {"txData": True, "rxData": True}
    for row in samples:
        if not isinstance(row, dict) or len(row) > 8:
            invalid += 1
            complete["txData"] = complete["rxData"] = False
            continue
        unknown += len(set(row) - _SAMPLE_FIELDS)
        if "time" not in row:
            missing += 1
        else:
            timestamp = row["time"]
            if type(timestamp) is not int or not 0 <= timestamp <= _INT64_MAX:
                invalid += 1
            else:
                timestamps.append(timestamp)
        for key in values:
            if key not in row:
                missing += 1
                complete[key] = False
                continue
            number = row[key]
            if type(number) not in (int, float) or number < 0:
                invalid += 1
                complete[key] = False
                continue
            try:
                finite_number = float(number)
            except OverflowError:
                invalid += 1
                complete[key] = False
                continue
            if not math.isfinite(finite_number):
                invalid += 1
                complete[key] = False
                continue
            values[key].append(finite_number)

    data: dict[str, object] = {"sample_count": len(samples)}
    if timestamps:
        data["earliest_sample_unix_seconds"] = min(timestamps)
        data["latest_sample_unix_seconds"] = max(timestamps)
    for key, label in (("txData", "uplink"), ("rxData", "downlink")):
        complete_metric = complete[key] and len(values[key]) == len(samples)
        data[f"mean_{label}_sample_mb_value"] = (
            sum(values[key]) / len(samples) if samples and complete_metric else None)
        data[f"peak_{label}_sample_mb_value"] = (
            max(values[key]) if samples and complete_metric else None)
    partial = bool(missing or invalid or unknown or not all(complete.values()))
    return data, missing, invalid, unknown, partial


def project_site_traffic_activity_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteTrafficActivitySummaryError("response_invalid")
    unknown = len(set(result) - _NETWORK_FIELDS)
    missing = invalid = 0
    partial = bool(unknown)
    data: dict[str, object] = {}
    for key, label in _NETWORKS.items():
        if key not in result:
            missing += 1
            partial = True
            data[f"{label}_traffic"] = None
            continue
        summary, row_missing, row_invalid, row_unknown, row_partial = (
            _summarize_samples(result[key]))
        missing += row_missing
        invalid += row_invalid
        unknown += row_unknown
        partial = partial or row_partial
        data[f"{label}_traffic"] = summary
    data.update({"missing_field_count": missing,
                 "invalid_field_count": invalid,
                 "unknown_field_count": unknown})
    return {"data": data, "partial": partial}
