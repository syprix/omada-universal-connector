"""Redacted coverage for the fixed Wi-Fi Calling top-SSID result."""
from __future__ import annotations

from typing import Any

MAX_TOP_SSID_ROWS = 10
MAX_ROW_FIELDS = 64
INT32_MIN, INT32_MAX = -(2**31), 2**31 - 1
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1

_FIELD_TYPES = {
    "clientName": "string", "apName": "string", "apMac": "string",
    "clientMac": "string", "ip": "string", "carrierName": "string",
    "wifiCallingProfileName": "string", "priority": "int32", "ssid": "string",
    "band": "int32", "domain": "string", "totalTraffic": "int64",
    "trafficDown": "int64", "trafficUp": "int64", "startTime": "int64",
    "endTime": "int64", "callNum": "int32", "deviceType": "string",
    "model": "string",
}


class WifiCallingTopSsidError(ValueError):
    """Invalid or overlarge top-SSID response."""


def _valid_type(value: Any, schema_type: str) -> bool:
    if schema_type == "string":
        return isinstance(value, str) and len(value) <= 4096
    if type(value) is not int:
        return False
    if schema_type == "int32":
        return INT32_MIN <= value <= INT32_MAX
    return INT64_MIN <= value <= INT64_MAX


def project_site_wifi_calling_top_ssid_summary(result: Any) -> dict[str, object]:
    """Count only topKSsids rows and documented field-shape coverage.

    The operation has no documented required row properties or total count.
    This projection therefore reports observed shape only; it never claims the
    top list or underlying Wi-Fi Calling telemetry is complete.
    """
    if not isinstance(result, dict):
        raise WifiCallingTopSsidError("result_invalid")

    if "topKSsids" not in result:
        state = "missing"
        rows: list[Any] | None = None
    else:
        source = result["topKSsids"]
        if not isinstance(source, list):
            state = "invalid"
            rows = None
        elif len(source) > MAX_TOP_SSID_ROWS:
            return {
                "top_ssid_source_state": "too_large",
                "source_scope": "topKSsids_only",
                "server_completeness_established": False,
                "top_ssid_row_count": len(source),
                "invalid_row_count": 0,
                "documented_field_count": len(_FIELD_TYPES),
                "documented_field_observed_count": 0,
                "documented_field_presence_count": 0,
                "documented_field_missing_count": 0,
                "documented_field_type_valid_count": 0,
                "documented_field_type_invalid_count": 0,
                "rows_with_all_documented_fields_count": 0,
                "unknown_field_count": 0,
                "partial": True,
            }
        else:
            rows = source
            state = "empty" if not rows else "present"

    if rows is None:
        return {
            "top_ssid_source_state": state,
            "source_scope": "topKSsids_only",
            "server_completeness_established": False,
            "top_ssid_row_count": None,
            "invalid_row_count": 0,
            "documented_field_count": len(_FIELD_TYPES),
            "documented_field_observed_count": 0,
            "documented_field_presence_count": 0,
            "documented_field_missing_count": 0,
            "documented_field_type_valid_count": 0,
            "documented_field_type_invalid_count": 0,
            "rows_with_all_documented_fields_count": 0,
            "unknown_field_count": 0,
            "partial": True,
        }

    invalid_rows = unknown_fields = field_presence = field_missing = 0
    field_type_valid = field_type_invalid = fully_covered_rows = 0
    observed_fields: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or len(row) > MAX_ROW_FIELDS:
            invalid_rows += 1
            continue
        unknown_fields += len(set(row) - set(_FIELD_TYPES))
        row_presence = row_missing = row_invalid = 0
        for field, schema_type in _FIELD_TYPES.items():
            if field not in row:
                row_missing += 1
                continue
            row_presence += 1
            observed_fields.add(field)
            if _valid_type(row[field], schema_type):
                field_type_valid += 1
            else:
                field_type_invalid += 1
                row_invalid += 1
        field_presence += row_presence
        field_missing += row_missing
        if row_missing == 0 and row_invalid == 0:
            fully_covered_rows += 1

    if invalid_rows or field_type_invalid:
        state = "invalid"
    return {
        "top_ssid_source_state": state,
        "source_scope": "topKSsids_only",
        "server_completeness_established": False,
        "top_ssid_row_count": len(rows),
        "invalid_row_count": invalid_rows,
        "documented_field_count": len(_FIELD_TYPES),
        "documented_field_observed_count": len(observed_fields),
        "documented_field_presence_count": field_presence,
        "documented_field_missing_count": field_missing,
        "documented_field_type_valid_count": field_type_valid,
        "documented_field_type_invalid_count": field_type_invalid,
        "rows_with_all_documented_fields_count": fully_covered_rows,
        "unknown_field_count": unknown_fields,
        "partial": bool(
            state not in {"empty", "present"} or invalid_rows or unknown_fields or
            field_missing or field_type_invalid),
    }
