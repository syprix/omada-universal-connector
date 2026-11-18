"""Redacted projection for the documented site dashboard channel statistics."""
from __future__ import annotations

import math


class ChannelDashboardError(ValueError):
    """Input exceeds safe bounds or is not a result object."""

    def __init__(self, code: str = "channel_dashboard_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_BAND_FIELDS = {
    "2g": "2g channel stat",
    "5g": "5g channel stat",
    "6g": "6g channel stat",
}
_BANDS = tuple(_BAND_FIELDS.values())
_FIELDS = ("channel", "apNum", "clientNum", "channelUtilization")
_MAX_FIELDS = 64
_MAX_ROWS_PER_BAND = 256
_INT32_MAX = 2_147_483_647


def _valid_count(value: object) -> bool:
    return type(value) is int and 0 <= value <= _INT32_MAX


def _valid_utilization(value: object) -> bool:
    if value is None:
        return True
    if type(value) not in (int, float) or not 0 <= value <= 100:
        return False
    return type(value) is int or math.isfinite(value)


def project_site_dashboard_channels(raw: object) -> dict[str, object]:
    """Project only the three documented per-band channel-stat arrays.

    Missing arrays and incomplete rows are represented as partial; an absent
    band is never silently turned into an empty observation. Unknown keys and
    values are counted but never returned.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise ChannelDashboardError()

    bands: dict[str, list[dict[str, object]]] = {}
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0

    for band in _BANDS:
        if band not in raw:
            missing.append(band)
            omitted_count += 1
            continue
        rows = raw[band]
        if not isinstance(rows, list):
            omitted.add(band)
            omitted_count += 1
            continue
        if len(rows) > _MAX_ROWS_PER_BAND:
            raise ChannelDashboardError()

        projected: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                omitted.add("invalid_rows")
                omitted_count += 1
                continue
            if len(row) > _MAX_FIELDS:
                raise ChannelDashboardError()
            out: dict[str, object] = {}
            for field in _FIELDS:
                if field not in row:
                    omitted.add(f"{band}.{field}")
                    omitted_count += 1
                    continue
                value = row[field]
                if field == "channelUtilization":
                    valid = _valid_utilization(value)
                else:
                    valid = _valid_count(value)
                if valid:
                    output_field = {
                        "apNum": "ap_count",
                        "clientNum": "client_count",
                        "channelUtilization": "utilization_percent",
                    }.get(field, field)
                    out[output_field] = value
                else:
                    omitted.add(f"{band}.{field}")
                    omitted_count += 1

            extras = sum(1 for key in row if key not in _FIELDS)
            if extras:
                omitted.add("unknown_fields")
                omitted_count += extras
            projected.append(out)
        bands[band.removesuffix(" channel stat")] = projected

    extras = sum(1 for key in raw if key not in _BANDS)
    if extras:
        omitted.add("unknown_fields")
        omitted_count += extras

    return {
        "status": "ok",
        "resource": "site_dashboard_channels",
        "data": {"bands": bands},
        "partial": bool(missing or omitted_count),
        "missing_fields": missing,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
    }
