"""Compact redacted WAN port rate and latency aggregates."""
from __future__ import annotations

from typing import Any


class SiteIspLoadSummaryError(ValueError):
    """Raised when the unpaged WAN load response is malformed or oversized."""


_PORT_FIELDS = {"portId", "portName", "data"}
_SAMPLE_FIELDS = {"totalRate", "latency", "time"}
_MAX_PORTS = 64
_MAX_SAMPLES = 5_000
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1


def project_site_isp_load_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > _MAX_PORTS:
        raise SiteIspLoadSummaryError("response_invalid")
    rates: list[int] = []
    latencies: list[int] = []
    timestamps: list[int] = []
    missing = invalid = unknown = sample_count = 0
    for port in result:
        if not isinstance(port, dict) or len(port) > 6:
            invalid += 1
            continue
        unknown += len(set(port) - _PORT_FIELDS)
        if "portId" in port and (type(port["portId"]) is not int or
                                 not 0 <= port["portId"] <= _INT32_MAX):
            invalid += 1
        if "portName" in port and not isinstance(port["portName"], str):
            invalid += 1
        if "data" not in port:
            missing += 1
            continue
        rows = port["data"]
        if not isinstance(rows, list) or len(rows) > _MAX_SAMPLES:
            raise SiteIspLoadSummaryError("response_invalid")
        if sample_count + len(rows) > _MAX_SAMPLES:
            raise SiteIspLoadSummaryError("response_invalid")
        sample_count += len(rows)
        for row in rows:
            if not isinstance(row, dict) or len(row) > 6:
                invalid += 1
                continue
            unknown += len(set(row) - _SAMPLE_FIELDS)
            values: dict[str, int] = {}
            for key in ("totalRate", "latency", "time"):
                if key not in row:
                    missing += 1
                    continue
                value = row[key]
                upper = _INT64_MAX if key in {"totalRate", "time"} else 1_000
                if type(value) is not int or not 0 <= value <= upper:
                    invalid += 1
                else:
                    values[key] = value
            if "totalRate" in values:
                rates.append(values["totalRate"])
            if "latency" in values:
                latencies.append(values["latency"])
            if "time" in values:
                timestamps.append(values["time"])
    complete = not (missing or invalid or unknown)
    data: dict[str, object] = {
        "port_count": len(result),
        "sample_count": sample_count,
        "mean_total_rate_value": (sum(rates) / len(rates)
                                  if rates and complete else None),
        "peak_total_rate_value": (max(rates) if rates and complete else None),
        "mean_latency_ms": (sum(latencies) / len(latencies)
                            if latencies and complete else None),
        "minimum_latency_ms": (min(latencies) if latencies and complete else None),
        "maximum_latency_ms": (max(latencies) if latencies and complete else None),
        "earliest_sample_unix_seconds": min(timestamps) if timestamps and complete else None,
        "latest_sample_unix_seconds": max(timestamps) if timestamps and complete else None,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
    }
    return {"data": data, "partial": not complete}
