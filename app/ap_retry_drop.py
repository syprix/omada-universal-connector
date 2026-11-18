"""Bounded, redacted projection of site dashboard AP retry/drop diagnostics."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

try:
    from .finite_values import is_finite_number
except ImportError:  # direct execution in the image
    from finite_values import is_finite_number


class ApRetryDropProjectionError(ValueError):
    """The retry/drop response or projection inputs have invalid shapes."""


MAX_AP_ROWS_PER_KIND = 128
MAX_SAMPLES_PER_AP = 256
_CANONICAL_MAC = re.compile(r"[0-9a-f]{12}\Z")
_RESPONSE_MAC = re.compile(r"(?:(?:[0-9A-Fa-f]{2}:){5}|(?:[0-9A-Fa-f]{2}-){5})[0-9A-Fa-f]{2}\Z")
_OPAQUE_REF = re.compile(r"[0-9a-f]{24}\Z")
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def _integer(value: Any, *, bits: int) -> bool:
    minimum, maximum = (_INT32_MIN, _INT32_MAX) if bits == 32 else (_INT64_MIN, _INT64_MAX)
    return type(value) is int and minimum <= value <= maximum


def _canonical_response_mac(value: object) -> str | None:
    if not isinstance(value, str) or not _RESPONSE_MAC.fullmatch(value):
        return None
    return value.replace(":", "").replace("-", "").lower()


def _inventory_refs(mapping: Mapping[str, object]) -> dict[str, str | None]:
    """Validate canonical MAC keys; None denotes an explicitly ambiguous MAC."""
    normalized: dict[str, str | None] = {}
    for mac, refs in mapping.items():
        if not isinstance(mac, str) or not _CANONICAL_MAC.fullmatch(mac):
            raise ApRetryDropProjectionError("inventory_mapping_invalid")
        if isinstance(refs, str):
            if not _OPAQUE_REF.fullmatch(refs):
                raise ApRetryDropProjectionError("inventory_mapping_invalid")
            normalized[mac] = refs
        elif isinstance(refs, (list, tuple, set, frozenset)):
            candidates = list(refs)
            if any(not isinstance(ref, str) or not _OPAQUE_REF.fullmatch(ref) for ref in candidates):
                raise ApRetryDropProjectionError("inventory_mapping_invalid")
            unique = set(candidates)
            normalized[mac] = next(iter(unique)) if len(unique) == 1 else None
        elif refs is None:
            normalized[mac] = None
        else:
            raise ApRetryDropProjectionError("inventory_mapping_invalid")
    return normalized


def _series(rows: object, *, count_key: str, rate_key: str,
            start_seconds: int, end_seconds: int) -> tuple[list[dict[str, int | float]], int, int]:
    if not isinstance(rows, list):
        raise ApRetryDropProjectionError("response_invalid")
    projected: list[dict[str, int | float]] = []
    omitted_outside = 0
    omitted_limit = max(0, len(rows) - MAX_SAMPLES_PER_AP)
    for point in rows[:MAX_SAMPLES_PER_AP]:
        if not isinstance(point, dict):
            raise ApRetryDropProjectionError("response_invalid")
        timestamp, count, rate = point.get("time"), point.get(count_key), point.get(rate_key)
        if (not _integer(timestamp, bits=64) or not _integer(count, bits=32) or count < 0 or
                not is_finite_number(rate)):
            raise ApRetryDropProjectionError("response_invalid")
        if not start_seconds <= timestamp <= end_seconds:
            omitted_outside += 1
            continue
        projected.append({"time_seconds": timestamp, "count": count, "rate": rate})
    return projected, omitted_outside, omitted_limit


def _project_ap(row: object, *, kind: str, start_seconds: int,
                end_seconds: int) -> tuple[dict[str, Any], int]:
    if not isinstance(row, dict):
        raise ApRetryDropProjectionError("response_invalid")
    output: dict[str, Any] = {}
    status = row.get("status")
    if status is not None:
        if not _integer(status, bits=32) or status not in (0, 1):
            raise ApRetryDropProjectionError("response_invalid")
        output["status"] = status
    if "avg" in row and row["avg"] is not None:
        if not is_finite_number(row["avg"]):
            raise ApRetryDropProjectionError("response_invalid")
        output["average_rate"] = row["avg"]

    series_key = "retries" if kind == "retry" else "dropouts"
    count_key, rate_key = (("retryTimes", "retryRate") if kind == "retry"
                           else ("dropTimes", "dropRate"))
    if series_key in row:
        series, outside, limited = _series(row[series_key], count_key=count_key,
                                           rate_key=rate_key,
                                           start_seconds=start_seconds,
                                           end_seconds=end_seconds)
    else:
        # The schema does not require the series property, but its absence means
        # this diagnostic row cannot be represented as complete.
        series, outside, limited = [], 0, 0
        output["missing_fields"] = [series_key]
    output["samples"] = series
    output["sample_count"] = len(row[series_key]) if series_key in row else 0
    if outside:
        output["omitted_out_of_window_sample_count"] = outside
    if limited:
        output["omitted_sample_count"] = limited
    omitted_identifying_fields = sum(
        1 for key in ("apMac", "name", "model", "modelVersion")
        if key in row and row[key] is not None
    )
    return output, outside + limited + omitted_identifying_fields + int(series_key not in row)


def project_ap_retry_drop(result: Any, start_seconds: int, end_seconds: int,
                          ap_refs_by_canonical_mac: Mapping[str, object]) -> dict[str, Any]:
    """Return bounded AP retry/drop data mapped to opaque inventory references.

    Mapping keys are exactly 12 lowercase hexadecimal MAC characters with no
    separators. A value is one 24-hex opaque AP reference, or multiple refs / None
    to indicate ambiguity. Response MACs may use colon or hyphen notation and are
    canonicalized before lookup. Names, raw identifiers, and addresses never escape.
    """
    if (not _integer(start_seconds, bits=64) or not _integer(end_seconds, bits=64) or
            start_seconds < 0 or end_seconds < start_seconds or
            not isinstance(ap_refs_by_canonical_mac, Mapping)):
        raise ApRetryDropProjectionError("input_invalid")
    inventory = _inventory_refs(ap_refs_by_canonical_mac)
    if not isinstance(result, dict):
        raise ApRetryDropProjectionError("response_invalid")

    output: dict[str, Any] = {
        "retry_aps": [], "dropped_aps": [], "retry_ap_count": 0,
        "dropped_ap_count": 0, "partial": False,
        "omitted_unknown_ap_count": 0, "omitted_ambiguous_ap_count": 0,
        "omitted_duplicate_ap_count": 0, "omitted_out_of_window_sample_count": 0,
        "omitted_identifying_field_count": 0,
    }
    partial = False
    for source_key, output_key, kind in (
        ("retryEaps", "retry_aps", "retry"),
        ("droppedEaps", "dropped_aps", "drop"),
    ):
        if source_key not in result:
            partial = True
            output["missing_fields"] = output.get("missing_fields", []) + [source_key]
            continue
        rows = result[source_key]
        if not isinstance(rows, list):
            raise ApRetryDropProjectionError("response_invalid")
        output[output_key[:-1] + "_count"] = len(rows)
        output["retry_ap_count" if kind == "retry" else "dropped_ap_count"] = len(rows)
        omitted_limit = max(0, len(rows) - MAX_AP_ROWS_PER_KIND)
        if omitted_limit:
            partial = True
        output["omitted_" + output_key + "_limit_count"] = omitted_limit
        seen: set[str] = set()
        projected_rows = output[output_key]
        for row in rows[:MAX_AP_ROWS_PER_KIND]:
            if not isinstance(row, dict):
                raise ApRetryDropProjectionError("response_invalid")
            mac = _canonical_response_mac(row.get("apMac"))
            if mac is None or mac not in inventory:
                output["omitted_unknown_ap_count"] += 1
                partial = True
                continue
            if inventory[mac] is None:
                output["omitted_ambiguous_ap_count"] += 1
                partial = True
                continue
            if mac in seen:
                output["omitted_duplicate_ap_count"] += 1
                partial = True
                continue
            seen.add(mac)
            projected, omission_count = _project_ap(row, kind=kind,
                                                    start_seconds=start_seconds,
                                                    end_seconds=end_seconds)
            projected["device_ref"] = inventory[mac]
            projected_rows.append(projected)
            if omission_count:
                partial = True
                output["omitted_identifying_field_count"] += sum(
                    1 for key in ("apMac", "name", "model", "modelVersion")
                    if key in row and row[key] is not None
                )
                if "missing_fields" in projected:
                    partial = True
                output["omitted_out_of_window_sample_count"] += projected.get(
                    "omitted_out_of_window_sample_count", 0)
    output["partial"] = partial
    return output
