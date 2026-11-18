"""Compact, identity-free client activity counts for a recent dashboard window."""
from __future__ import annotations

from typing import Any


class SiteClientActivitySummaryError(ValueError):
    """Raised when the unpaged dashboard activity response is malformed or oversized."""


_FIELDS = {
    "time", "newEapClientNum", "newSwitchClientNum", "activeEapClientNum",
    "activeSwitchClientNum", "disconnectEapClientNum", "disconnectSwitchClientNum",
}
_COUNTS = {
    "newEapClientNum": ("new_eap_clients", "new"),
    "newSwitchClientNum": ("new_switch_clients", "new"),
    "activeEapClientNum": ("active_eap_clients", "active"),
    "activeSwitchClientNum": ("active_switch_clients", "active"),
    "disconnectEapClientNum": ("disconnected_eap_clients", "disconnected"),
    "disconnectSwitchClientNum": ("disconnected_switch_clients", "disconnected"),
}
_MAX_ROWS = 2_000
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1


def project_site_client_activity_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_ROWS:
        raise SiteClientActivitySummaryError("response_invalid")

    missing = invalid = unknown = 0
    timestamps: list[int] = []
    values: dict[str, list[int]] = {key: [] for key in _COUNTS}
    complete = {key: True for key in _COUNTS}
    for row in result:
        if not isinstance(row, dict) or len(row) > 10:
            invalid += 1
            for key in complete:
                complete[key] = False
            continue
        unknown += len(set(row) - _FIELDS)
        if "time" not in row:
            missing += 1
        else:
            timestamp = row["time"]
            if type(timestamp) is not int or not 0 <= timestamp <= _INT64_MAX:
                invalid += 1
            else:
                timestamps.append(timestamp)
        for key in _COUNTS:
            if key not in row:
                missing += 1
                complete[key] = False
                continue
            value = row[key]
            if type(value) is not int or not 0 <= value <= _INT32_MAX:
                invalid += 1
                complete[key] = False
            else:
                values[key].append(value)

    data: dict[str, object] = {"sample_count": len(result)}
    if timestamps:
        data["first_sample_time"] = min(timestamps)
        data["last_sample_time"] = max(timestamps)

    for field, (label, category) in _COUNTS.items():
        samples = values[field]
        is_complete = complete[field] and len(samples) == len(result)
        if category == "active":
            data[f"mean_{label}_per_sample"] = (
                sum(samples) / len(result) if result and is_complete else None)
            data[f"peak_{label}_per_sample"] = (
                max(samples) if result and is_complete else None)
        else:
            data[f"total_{label}"] = sum(samples) if is_complete else None
            data[f"peak_{label}_per_sample"] = (
                max(samples) if result and is_complete else None)

    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or not all(complete.values())),
    }
