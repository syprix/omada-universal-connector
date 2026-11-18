"""Bounded projection for site-wide incident overview statistics."""
from __future__ import annotations

import re
from typing import Any


MAX_INT32 = 2_147_483_647
WINDOW_MS = 86_400_000
MAX_SOURCE_FIELDS = 32
MAX_CATEGORIES = 128
MAX_CATEGORY_FIELDS = 12
_ANOMALY_CODE = re.compile(r"[A-Za-z0-9_.-]{1,64}")

COUNT_FIELDS = {
    "allStatus": "all_status",
    "ongoing": "ongoing",
    "resolved": "resolved",
    "ignored": "ignored",
    "unresolved": "unresolved",
    "all": "all_categories",
    "security": "security",
    "deviceStatus": "device_status",
    "wanAndServices": "wan_and_services",
    "link": "link",
    "wiredNetwork": "wired_network",
    "wirelessNetwork": "wireless_network",
    "roaming": "roaming",
    "authentication": "authentication",
    "access": "access",
    "allLevel": "all_levels",
    "critical": "critical",
    "error": "error",
    "warning": "warning",
    "info": "info",
    "others": "deprecated_others",
}
CATEGORY_FIELDS = {
    "counts": "active_count",
    "totalCounts": "total_count",
    "currentStatusCounts": "current_status_count",
    "influencingDevices": "influencing_device_count",
    "influencingClients": "influencing_client_count",
    "level": "level_code",
}


class SiteIncidentOverviewError(ValueError):
    """Raised when a response exceeds the bounded projection limits."""


def _valid_count(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_INT32


def project_site_incident_overview(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise SiteIncidentOverviewError("response_invalid")

    counts: dict[str, int] = {}
    invalid_count = 0
    for source, target in COUNT_FIELDS.items():
        if source not in result:
            continue
        value = result[source]
        if _valid_count(value):
            counts[target] = value
        else:
            invalid_count += 1

    category_counts: list[dict[str, object]] = []
    unknown_count = 0
    category_missing_count = 0
    category_present = "anomalyCategoryEventCounts" in result
    category_rows = result.get("anomalyCategoryEventCounts")
    if category_present:
        if not isinstance(category_rows, list) or len(category_rows) > MAX_CATEGORIES:
            invalid_count += 1
            category_rows = []
        for row in category_rows:
            if not isinstance(row, dict) or len(row) > MAX_CATEGORY_FIELDS:
                invalid_count += 1
                continue
            code = row.get("anomalyCode")
            code_valid = isinstance(code, str) and _ANOMALY_CODE.fullmatch(code) is not None
            unknown_count += len(set(row) - set(CATEGORY_FIELDS) - {"anomalyCode"})
            projected: dict[str, object] = {}
            row_invalid = 0
            for source, target in CATEGORY_FIELDS.items():
                if source not in row:
                    continue
                value = row[source]
                if _valid_count(value):
                    projected[target] = value
                else:
                    row_invalid += 1
            if not code_valid:
                row_invalid += 1
            projected["anomaly_code"] = code if code_valid else None
            present_fields = sum(source in row for source in CATEGORY_FIELDS) + int("anomalyCode" in row)
            projected["missing_count"] = (len(CATEGORY_FIELDS) + 1) - present_fields
            projected["invalid_count"] = row_invalid
            category_missing_count += projected["missing_count"]
            category_counts.append(projected)
            invalid_count += row_invalid

    unknown_fields = set(result) - set(COUNT_FIELDS) - {"anomalyCategoryEventCounts"}
    missing_count = (len(COUNT_FIELDS) - sum(name in result for name in COUNT_FIELDS))
    missing_count += category_missing_count
    if not category_present:
        missing_count += 1
    unknown_count += len(unknown_fields)
    return {
        "data": {
            "counts": counts,
            "category_counts": category_counts,
            "present_count": len(counts),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
