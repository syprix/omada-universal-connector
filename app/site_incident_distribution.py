"""Bounded projection for site incident distribution statistics."""
from __future__ import annotations

from typing import Any


WINDOW_MS = 86_400_000
MAX_INT32 = 2_147_483_647
MAX_INT64 = 9_223_372_036_854_775_807
MAX_SOURCE_FIELDS = 8
MAX_POINTS = 128

COUNT_FIELDS = {
    "critical": "critical",
    "error": "error",
    "warning": "warning",
    "info": "info",
    "access": "access",
    "authentication": "authentication",
    "roaming": "roaming",
    "wirelessNetwork": "wireless_network",
    "wiredNetwork": "wired_network",
    "link": "link",
    "wanAndServices": "wan_and_services",
    "deviceStatus": "device_status",
    "security": "security",
    "all": "all",
}


class SiteIncidentDistributionError(ValueError):
    """Raised when a response exceeds the bounded projection limits."""


def project_site_incident_distribution(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise SiteIncidentDistributionError("response_invalid")

    rows_present = "incidentCounts" in result
    rows = result.get("incidentCounts")
    invalid_count = 0
    unknown_count = 0
    missing_count = 0 if rows_present else 1
    points: list[dict[str, object]] = []

    if rows_present:
        if not isinstance(rows, list):
            invalid_count += 1
            rows = []
        elif len(rows) > MAX_POINTS:
            raise SiteIncidentDistributionError("response_invalid")
        for row in rows:
            if not isinstance(row, dict) or len(row) > len(COUNT_FIELDS) + 1:
                invalid_count += 1
                continue
            unknown_count += len(set(row) - set(COUNT_FIELDS) - {"time"})
            point: dict[str, object] = {"counts": {}}
            counts = point["counts"]
            for source, target in COUNT_FIELDS.items():
                if source not in row:
                    missing_count += 1
                    continue
                value = row[source]
                if type(value) is int and 0 <= value <= MAX_INT32:
                    counts[target] = value
                else:
                    invalid_count += 1
            time_value = row.get("time")
            if type(time_value) is int and 0 <= time_value <= MAX_INT64:
                point["time_seconds"] = time_value
            else:
                invalid_count += 1
                point["time_seconds"] = None
            if "time" not in row:
                missing_count += 1
            points.append(point)

    unknown_count += len(set(result) - {"incidentCounts"})
    return {
        "data": {
            "points": points,
            "point_count": len(points),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
