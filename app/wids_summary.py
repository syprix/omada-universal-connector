"""Redacted summaries of Wireless IDS rows returned by the site API."""
from __future__ import annotations


class WidsSummaryError(ValueError):
    """The Wireless IDS response is outside the documented bounds."""


MAX_PAGE_SIZE = 1_000
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_KNOWN_FIELDS = frozenset({
    "stationMac", "stationMacList", "detectMac", "channel", "band",
    "startTime", "type", "level",
})
_MAC_FIELDS = frozenset({"stationMac", "detectMac"})
_BLACKLIST_FIELDS = frozenset({"stationMac", "detectMac", "timeStamp"})


def summarize_wids_results(rows: object, total_rows: object) -> dict[str, object]:
    """Aggregate one bounded page without returning station or AP identities.

    The API documents the numeric severity and band codes but does not define
    event-type meanings or timestamp units. Those values stay as raw codes;
    timestamps and MAC addresses are validated for shape and then discarded.
    """
    if (not isinstance(rows, list) or len(rows) > MAX_PAGE_SIZE or
            type(total_rows) is not int or total_rows < len(rows)):
        raise WidsSummaryError()

    by_level: dict[int, int] = {}
    by_type: dict[int, int] = {}
    by_band: dict[int, int] = {}
    by_channel: dict[int, int] = {}
    unknown_level_count = 0
    unknown_band_count = 0
    invalid_field_count = 0
    unknown_field_count = 0
    unknown_row_count = 0

    def integer(row: dict[str, object], key: str, minimum: int, maximum: int) -> int | None:
        nonlocal invalid_field_count
        if key not in row:
            return None
        value = row[key]
        if type(value) is not int or not minimum <= value <= maximum:
            invalid_field_count += 1
            return None
        return value

    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            unknown_row_count += 1
            continue
        unknown_field_count += sum(1 for key in row if key not in _KNOWN_FIELDS)
        for key in _MAC_FIELDS:
            if key in row and (not isinstance(row[key], str) or len(row[key]) > 64):
                invalid_field_count += 1
        if "stationMacList" in row:
            value = row["stationMacList"]
            if (not isinstance(value, list) or len(value) > 256 or
                    any(not isinstance(item, str) or len(item) > 64 for item in value)):
                invalid_field_count += 1
        integer(row, "startTime", _INT64_MIN, _INT64_MAX)
        level = integer(row, "level", _INT32_MIN, _INT32_MAX)
        if level is not None:
            if level in (0, 1, 2):
                by_level[level] = by_level.get(level, 0) + 1
            else:
                unknown_level_count += 1
        event_type = integer(row, "type", _INT32_MIN, _INT32_MAX)
        if event_type is not None:
            by_type[event_type] = by_type.get(event_type, 0) + 1
        band = integer(row, "band", _INT32_MIN, _INT32_MAX)
        if band is not None:
            if band in (0, 1, 2, 3):
                by_band[band] = by_band.get(band, 0) + 1
            else:
                unknown_band_count += 1
        channel = integer(row, "channel", _INT32_MIN, _INT32_MAX)
        if channel is not None:
            by_channel[channel] = by_channel.get(channel, 0) + 1

    partial = bool(total_rows > len(rows) or unknown_level_count or unknown_band_count or
                   invalid_field_count or unknown_field_count or unknown_row_count)
    return {
        "status": "ok",
        "resource": "site_wids_summary",
        "count": len(rows),
        "total_rows": total_rows,
        "summary": {
            "by_level_code": dict(sorted(by_level.items())),
            "by_type_code": dict(sorted(by_type.items())),
            "by_band_code": dict(sorted(by_band.items())),
            "by_channel": dict(sorted(by_channel.items())),
            "unknown_level_count": unknown_level_count,
            "unknown_band_count": unknown_band_count,
            "invalid_field_count": invalid_field_count,
            "unknown_field_count": unknown_field_count,
            "unknown_row_count": unknown_row_count,
        },
        "partial": partial,
    }


def summarize_wids_blacklist(rows: object, total_rows: object) -> dict[str, object]:
    """Count one bounded dynamic blacklist page without returning identities."""
    if (not isinstance(rows, list) or len(rows) > MAX_PAGE_SIZE or
            type(total_rows) is not int or total_rows < len(rows)):
        raise WidsSummaryError()

    invalid_field_count = 0
    unknown_field_count = 0
    unknown_row_count = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 16:
            unknown_row_count += 1
            continue
        unknown_field_count += sum(1 for key in row if key not in _BLACKLIST_FIELDS)
        for key in _MAC_FIELDS:
            if key in row and (not isinstance(row[key], str) or len(row[key]) > 64):
                invalid_field_count += 1
        if "timeStamp" in row:
            value = row["timeStamp"]
            if type(value) is not int or not _INT64_MIN <= value <= _INT64_MAX:
                invalid_field_count += 1

    partial = bool(total_rows > len(rows) or invalid_field_count or
                   unknown_field_count or unknown_row_count)
    return {
        "status": "ok",
        "resource": "site_wids_blacklist_summary",
        "count": len(rows),
        "total_rows": total_rows,
        "summary": {
            "invalid_field_count": invalid_field_count,
            "unknown_field_count": unknown_field_count,
            "unknown_row_count": unknown_row_count,
        },
        "partial": partial,
    }
