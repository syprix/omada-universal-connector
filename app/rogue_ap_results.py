"""Redacted summaries of previously stored rogue AP scan results."""
from __future__ import annotations


class RogueApResultsError(ValueError):
    """Input is outside the documented stored-result bounds."""


_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_MAX_ROWS = 10_000
_SECURITY_CODES = frozenset({0, 1, 2, 3, 4, 15})
_MODE_CODES = frozenset(range(8))
_RADIO_IDS = frozenset(range(4))
_KNOWN_FIELDS = frozenset({
    "id", "ssid", "bssid", "radioId", "security", "beacon", "channel",
    "nearestApMac", "nearestAp", "mode", "signal", "lastSeen",
})


def summarize_rogue_ap_results(rows: object) -> dict[str, object]:
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise RogueApResultsError()
    radios: dict[int, int] = {}
    channels: dict[int, int] = {}
    security: dict[int, int] = {}
    modes: dict[int, int] = {}
    signals: list[int] = []
    invalid_field_count = 0
    unknown_field_count = 0
    unknown_row_count = 0
    unknown_radio_count = 0
    unknown_security_count = 0
    unknown_mode_count = 0

    def code(row: dict[str, object], field: str) -> int | None:
        nonlocal invalid_field_count
        if field not in row:
            return None
        value = row[field]
        if type(value) is not int or not _INT32_MIN <= value <= _INT32_MAX:
            invalid_field_count += 1
            return None
        return value

    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            unknown_row_count += 1
            continue
        unknown_field_count += sum(1 for key in row if key not in _KNOWN_FIELDS)
        radio = code(row, "radioId")
        if radio is not None:
            if radio in _RADIO_IDS:
                radios[radio] = radios.get(radio, 0) + 1
            else:
                unknown_radio_count += 1
        channel = code(row, "channel")
        if channel is not None:
            channels[channel] = channels.get(channel, 0) + 1
        security_code = code(row, "security")
        if security_code is not None:
            if security_code in _SECURITY_CODES:
                security[security_code] = security.get(security_code, 0) + 1
            else:
                unknown_security_count += 1
        mode = code(row, "mode")
        if mode is not None:
            if mode in _MODE_CODES:
                modes[mode] = modes.get(mode, 0) + 1
            else:
                unknown_mode_count += 1
        signal = code(row, "signal")
        if signal is not None:
            signals.append(signal)

    summary: dict[str, object] = {
        "by_radio_id": dict(sorted(radios.items())),
        "by_channel": dict(sorted(channels.items())),
        "by_security_code": dict(sorted(security.items())),
        "by_mode_code": dict(sorted(modes.items())),
        "unknown_radio_count": unknown_radio_count,
        "unknown_security_count": unknown_security_count,
        "unknown_mode_count": unknown_mode_count,
        "unknown_row_count": unknown_row_count,
        "invalid_field_count": invalid_field_count,
        "unknown_field_count": unknown_field_count,
    }
    if signals:
        summary["signal_dbm"] = {
            "minimum": min(signals), "maximum": max(signals),
            "average": round(sum(signals) / len(signals), 1), "sample_count": len(signals),
        }
    else:
        summary["signal_dbm"] = {"sample_count": 0}
    partial = bool(unknown_radio_count or unknown_security_count or unknown_mode_count or
                   unknown_row_count or invalid_field_count or unknown_field_count)
    return {"status": "ok", "resource": "site_rogue_ap_results", "count": len(rows),
            "summary": summary, "partial": partial, "data_age": "unknown_stored_scan"}
