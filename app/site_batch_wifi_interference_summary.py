"""Summarize a bounded batch Wi-Fi interference page without SSID identity."""
from __future__ import annotations

from collections.abc import Mapping


class SiteBatchWifiInterferenceSummaryError(ValueError):
    """The documented batch Wi-Fi interference result is malformed."""


PAGE_SIZE = 100
MAX_INT32 = 2_147_483_647
MAX_INT64 = 9_223_372_036_854_775_807
_ENVELOPE_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_ROW_FIELDS = frozenset((
    "id", "bssid", "ssid", "radioId", "channel", "mode", "security",
    "beacon", "signal", "lastSeen", "nearestAp", "bandWidth",
))
_STRING_FIELDS = frozenset(("id", "bssid", "ssid", "nearestAp"))


def _int(value: object, maximum: int, minimum: int = 0) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _increment(counts: dict[str, int], value: int) -> None:
    key = str(value)
    counts[key] = counts.get(key, 0) + 1


def summarize_site_batch_wifi_interferences(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 16:
        raise SiteBatchWifiInterferenceSummaryError("result must be a bounded object")
    missing = invalid = 0
    unknown = sum(key not in _ENVELOPE_FIELDS for key in value)

    total_rows = value.get("totalRows")
    if total_rows is None:
        missing += 1
    elif not _int(total_rows, MAX_INT64):
        invalid += 1
        total_rows = None
    current_page = value.get("currentPage")
    if current_page is None:
        missing += 1
    elif not _int(current_page, MAX_INT32):
        invalid += 1
        current_page = None
    elif current_page != 1:
        invalid += 1
    current_size = value.get("currentSize")
    if current_size is None:
        missing += 1
    elif not _int(current_size, MAX_INT32):
        invalid += 1
        current_size = None

    rows = value.get("data")
    if rows is None:
        missing += 1
        rows = []
    if not isinstance(rows, list):
        raise SiteBatchWifiInterferenceSummaryError("data must be a list")
    truncated = len(rows) > PAGE_SIZE
    returned = len(rows)
    page_rows = rows[:PAGE_SIZE]
    radio_counts: dict[str, int] = {}
    channel_counts: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    security_counts: dict[str, int] = {}
    signal_values: list[int] = []
    invalid_rows = unknown_rows = 0

    for row in page_rows:
        if not isinstance(row, Mapping) or len(row) > 32:
            invalid_rows += 1
            continue
        unknown_rows += sum(key not in _ROW_FIELDS for key in row)
        for field in _STRING_FIELDS:
            if field in row and not isinstance(row[field], str):
                invalid_rows += 1
        for field, counts, allowed in (
                ("radioId", radio_counts, frozenset((0, 1, 3))),
                ("channel", channel_counts, None),
                ("mode", mode_counts, None),
                ("security", security_counts, frozenset(range(10)))):
            if field not in row:
                continue
            number = row[field]
            if not _int(number, MAX_INT32):
                invalid_rows += 1
            elif allowed is not None and number not in allowed:
                unknown_rows += 1
            else:
                _increment(counts, number)
        for field in ("beacon", "bandWidth"):
            if field in row and not _int(row[field], MAX_INT32):
                invalid_rows += 1
        if "signal" in row:
            signal = row["signal"]
            if type(signal) is int and -(1 << 31) <= signal <= MAX_INT32:
                signal_values.append(signal)
            else:
                invalid_rows += 1
        if "lastSeen" in row and not _int(row["lastSeen"], MAX_INT64):
            invalid_rows += 1

    more = None if total_rows is None else total_rows > returned
    if total_rows is not None and total_rows < returned:
        invalid += 1
    coverage_unknown = total_rows is None
    return {
        "data": {
            "total_rows": total_rows,
            "page": current_page,
            "page_size": current_size,
            "returned_interference_count": returned,
            "processed_interference_count": len(page_rows),
            "has_more": more,
            "coverage_unknown": coverage_unknown,
            "radio_id_counts": radio_counts,
            "channel_counts": channel_counts,
            "phy_mode_counts": mode_counts,
            "security_type_counts": security_counts,
            "signal_reading_count": len(signal_values),
            "signal_min": min(signal_values) if signal_values else None,
            "signal_max": max(signal_values) if signal_values else None,
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid + invalid_rows,
        "unknown_field_count": unknown + unknown_rows,
        "partial": bool(missing or invalid or invalid_rows or unknown or
                        unknown_rows or truncated or coverage_unknown or more),
    }
