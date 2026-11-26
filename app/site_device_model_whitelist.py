"""Bounded, value-free coverage for the documented site device whitelist."""
from __future__ import annotations

from typing import Any


MAX_RECORDS = 512
MAX_RECORD_FIELDS = 32
KNOWN_FIELDS = {"model", "hwVersion"}


class SiteDeviceWhitelistError(ValueError):
    """Raised when the fixed whitelist response is malformed or over bound."""


def _coverage(rows: list[Any], field: str, unreadable: int) -> dict[str, int]:
    valid = missing = invalid = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if field not in row:
            missing += 1
            continue
        value = row[field]
        if isinstance(value, str) and value.strip():
            valid += 1
        else:
            invalid += 1
    return {"valid_count": valid, "missing_count": missing,
            "invalid_count": invalid, "uninspected_record_count": unreadable}


def summarize_site_device_whitelist(result: Any) -> dict[str, object]:
    """Summarize only row and documented field coverage, never values."""
    if not isinstance(result, list) or len(result) > MAX_RECORDS:
        raise SiteDeviceWhitelistError("response_invalid")

    unreadable = unknown = complete = 0
    for row in result:
        if not isinstance(row, dict):
            unreadable += 1
            continue
        if len(row) > MAX_RECORD_FIELDS:
            raise SiteDeviceWhitelistError("response_invalid")
        unknown += len(set(row) - KNOWN_FIELDS)
        model = row.get("model")
        hw_version = row.get("hwVersion")
        if (isinstance(model, str) and model.strip() and
                isinstance(hw_version, str) and hw_version.strip()):
            complete += 1

    model_coverage = _coverage(result, "model", unreadable)
    hardware_version_coverage = _coverage(result, "hwVersion", unreadable)
    partial = bool(
        unreadable or unknown or model_coverage["missing_count"] or
        model_coverage["invalid_count"] or
        hardware_version_coverage["missing_count"] or
        hardware_version_coverage["invalid_count"])
    return {
        "data": {
            "record_count": len(result),
            "empty": not result,
            "known_fields_complete_count": complete,
            "model_coverage": model_coverage,
            "hardware_version_coverage": hardware_version_coverage,
            "unreadable_record_count": unreadable,
            "unknown_field_count": unknown,
            "truncation_status": "not_reported_by_contract",
        },
        "partial": partial,
    }
