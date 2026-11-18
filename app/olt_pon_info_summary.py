"""Redacted OLT PON information and refresh-preference projections."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


MAX_PORTS = 64
MAX_FIELDS = 16
MAX_INT32 = 2_147_483_647
MAX_BANDWIDTH_KBPS = 1_310_720
_PON_FIELDS = {
    "portId", "onuNum", "status", "maxBandwidth", "actualBandwidth",
    "remainBandwidth", "opticalVcc", "opticalBias", "opticalPower",
}
_MEASUREMENTS = {
    "opticalVcc": "voltage", "opticalBias": "current", "opticalPower": "power",
}


class OltPonInfoError(ValueError):
    """Raised when PON information exceeds documented response bounds."""


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _valid_int(value: Any, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def project_olt_auto_refresh_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise OltPonInfoError("response_invalid")
    allowed = {"autoRefresh", "refreshInterval"}
    missing = 0
    invalid = 0
    unknown = len(set(result) - allowed)
    data: dict[str, object] = {}
    redacted = 0
    enabled = result.get("autoRefresh")
    if enabled is None:
        missing += 1
    elif isinstance(enabled, str) and enabled in {"ENABLE", "DISABLE"}:
        data["auto_refresh_enabled"] = enabled == "ENABLE"
        redacted += 1
    else:
        invalid += 1
    interval = result.get("refreshInterval")
    if interval is None:
        missing += 1
    elif _valid_int(interval, MAX_INT32):
        data["refresh_interval"] = interval
        redacted += 1
    else:
        invalid += 1
    return {"data": data, "partial": bool(missing or invalid or unknown),
            "missing_count": missing, "invalid_count": invalid,
            "unknown_field_count": unknown, "redacted_field_count": redacted}


def project_olt_pon_information_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_PORTS:
        raise OltPonInfoError("response_invalid")
    invalid = 0
    missing = 0
    unknown = 0
    redacted = 0
    enabled: dict[str, int] = {}
    onu_total = 0
    onu_count_ports = 0
    bandwidth_totals: dict[str, int] = {}
    bandwidth_counts: dict[str, int] = {}
    measurement_ranges: dict[str, dict[str, Decimal]] = {}
    measurement_counts: dict[str, int] = {}
    for row in result:
        if not isinstance(row, dict) or len(row) > MAX_FIELDS:
            invalid += 1
            continue
        unknown += len(set(row) - _PON_FIELDS)
        redacted += len(row)
        port_id = row.get("portId")
        if port_id is not None and (not isinstance(port_id, str) or len(port_id) > 128):
            invalid += 1
        status = row.get("status")
        if status is None:
            missing += 1
        elif isinstance(status, str) and status in {"ENABLE", "DISABLE"}:
            _increment(enabled, status)
        else:
            invalid += 1
        onu_num = row.get("onuNum")
        if onu_num is None:
            missing += 1
        elif _valid_int(onu_num, MAX_INT32):
            onu_total += onu_num
            onu_count_ports += 1
        else:
            invalid += 1
        for field in ("maxBandwidth", "actualBandwidth", "remainBandwidth"):
            value = row.get(field)
            if value is None:
                missing += 1
            elif _valid_int(value, MAX_BANDWIDTH_KBPS):
                bandwidth_totals[field] = bandwidth_totals.get(field, 0) + value
                _increment(bandwidth_counts, field)
            else:
                invalid += 1
        for field, name in _MEASUREMENTS.items():
            value = row.get(field)
            if value is None:
                missing += 1
                continue
            if not isinstance(value, str) or len(value) > 32:
                invalid += 1
                continue
            try:
                measurement = Decimal(value)
            except InvalidOperation:
                invalid += 1
                continue
            if not measurement.is_finite() or abs(measurement) > Decimal("10000"):
                invalid += 1
                continue
            bounds = measurement_ranges.setdefault(name, {"min": measurement, "max": measurement})
            bounds["min"] = min(bounds["min"], measurement)
            bounds["max"] = max(bounds["max"], measurement)
            _increment(measurement_counts, name)
    data = {
        "pon_port_count": len(result),
        "laser_state_counts": enabled,
        "onu_count": onu_total,
        "onu_count_reported_port_count": onu_count_ports,
        "bandwidth_totals_kbps": bandwidth_totals,
        "bandwidth_reported_port_counts": bandwidth_counts,
        "optical_measurement_ranges": {
            name: {bound: str(value) for bound, value in values.items()}
            for name, values in measurement_ranges.items()
        },
        "optical_measurement_counts": measurement_counts,
    }
    return {"data": data, "partial": bool(missing or invalid or unknown),
            "missing_count": missing, "invalid_count": invalid,
            "unknown_field_count": unknown, "redacted_field_count": redacted}
