"""Bounded projection for site incident category aggregates."""
from __future__ import annotations

import re
from typing import Any


MAX_INT32 = 2_147_483_647
MAX_CATEGORIES = 128
MAX_CATEGORY_FIELDS = 8
_ANOMALY_CODE = re.compile(r"[A-Za-z0-9_.-]{1,64}")

COUNT_FIELDS = {
    "counts": "active_count",
    "totalCounts": "total_count",
    "currentStatusCounts": "current_status_count",
    "influencingDevices": "influencing_device_count",
    "influencingClients": "influencing_client_count",
    "level": "level_code",
}


class SiteIncidentCategoryCountsError(ValueError):
    """Raised when the category response exceeds projection bounds."""


def project_site_incident_category_counts(result: Any) -> dict[str, object]:
    if not isinstance(result, list):
        raise SiteIncidentCategoryCountsError("response_invalid")
    if len(result) > MAX_CATEGORIES:
        raise SiteIncidentCategoryCountsError("response_invalid")

    rows: list[dict[str, object]] = []
    invalid_count = 0
    unknown_count = 0
    missing_count = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > MAX_CATEGORY_FIELDS:
            invalid_count += 1
            continue
        unknown_count += len(set(row) - set(COUNT_FIELDS) - {"anomalyCode"})
        code = row.get("anomalyCode")
        code_valid = isinstance(code, str) and _ANOMALY_CODE.fullmatch(code) is not None
        projected: dict[str, object] = {"anomaly_code": code if code_valid else None,
                                        "counts": {}}
        counts = projected["counts"]
        row_invalid = 0
        for source, target in COUNT_FIELDS.items():
            if source not in row:
                missing_count += 1
                continue
            value = row[source]
            if type(value) is int and 0 <= value <= MAX_INT32 and \
                    (source != "level" or value <= 3):
                counts[target] = value
            else:
                row_invalid += 1
        if "anomalyCode" not in row:
            missing_count += 1
        elif not code_valid:
            row_invalid += 1
        invalid_count += row_invalid
        rows.append(projected)

    return {
        "data": {
            "categories": rows,
            "category_count": len(rows),
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count),
    }
