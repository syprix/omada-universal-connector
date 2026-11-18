"""Bounded and identity-redacted projection for a site incident page."""
from __future__ import annotations

import re
from typing import Any


MAX_INT32 = 2_147_483_647
MAX_INT64 = 9_223_372_036_854_775_807
PAGE_SIZE = 50
WINDOW_MS = 86_400_000
MAX_ENVELOPE_FIELDS = 12
MAX_ROW_FIELDS = 24
_ANOMALY_CODE = re.compile(r"[A-Za-z0-9_.-]{1,64}")

ROW_FIELDS = {
    "category": "category_code",
    "level": "severity_code",
    "count": "occurrence_count",
    "status": "status_code",
    "firstTime": "first_time_ms",
    "lastTime": "last_time_ms",
}


class SiteIncidentListError(ValueError):
    """Raised when an incident page exceeds projection bounds."""


def _int(value: Any, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def project_site_incident_list(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_ENVELOPE_FIELDS:
        raise SiteIncidentListError("response_invalid")

    metadata: dict[str, object] = {}
    missing_count = 0
    invalid_count = 0
    unknown_count = len(set(result) - {"totalRows", "currentPage", "currentSize", "data", "statistic"})
    for source, target, maximum in (
        ("totalRows", "total_rows", MAX_INT64),
        ("currentPage", "current_page", MAX_INT32),
        ("currentSize", "current_size", MAX_INT32),
    ):
        if source not in result:
            missing_count += 1
        elif _int(result[source], maximum):
            metadata[target] = result[source]
        else:
            invalid_count += 1

    data_present = "data" in result
    raw_rows = result.get("data")
    rows: list[dict[str, object]] = []
    if not data_present:
        missing_count += 1
        raw_rows = []
    elif not isinstance(raw_rows, list):
        invalid_count += 1
        raw_rows = []
    elif len(raw_rows) > PAGE_SIZE:
        raise SiteIncidentListError("response_invalid")

    for raw in raw_rows:
        if not isinstance(raw, dict) or len(raw) > MAX_ROW_FIELDS:
            invalid_count += 1
            continue
        unknown_count += len(set(raw) - set(ROW_FIELDS) - {"anomalyCode"})
        code = raw.get("anomalyCode")
        code_valid = isinstance(code, str) and _ANOMALY_CODE.fullmatch(code) is not None
        projected: dict[str, object] = {"anomaly_code": code if code_valid else None}
        for source, target in ROW_FIELDS.items():
            if source not in raw:
                missing_count += 1
                continue
            value = raw[source]
            maximum = MAX_INT64 if source in ("firstTime", "lastTime") else MAX_INT32
            if _int(value, maximum) and (source != "status" or value <= 2) and \
                    (source != "level" or value <= 3):
                projected[target] = value
            else:
                invalid_count += 1
        if "anomalyCode" not in raw:
            missing_count += 1
        elif not code_valid:
            invalid_count += 1
        rows.append(projected)

    if isinstance(metadata.get("total_rows"), int):
        current_page = metadata.get("current_page")
        current_size = metadata.get("current_size")
        boundary = (current_page * current_size
                    if isinstance(current_page, int) and isinstance(current_size, int)
                    else len(rows))
        has_more = metadata["total_rows"] > boundary
    else:
        has_more = False
    return {
        "data": {
            **metadata,
            "incidents": rows,
            "returned_count": len(rows),
            "has_more": has_more,
            "missing_count": missing_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_count,
        },
        "partial": bool(missing_count or invalid_count or unknown_count or has_more),
    }
