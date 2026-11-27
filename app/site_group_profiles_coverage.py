"""Redacted bounded schema coverage for the fixed site group-profiles list."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_GROUP_PROFILE_ROWS = 500
_MAX_FIELDS = 32
_INT32_MIN = -(1 << 31)
_INT32_MAX = (1 << 31) - 1
_STRING_FIELDS = ("groupId", "name", "description")
_INT32_FIELDS = ("type", "count", "portType")
_BOOL_FIELDS = ("buildIn",)
_LIST_FIELDS = ("ipList", "ipv6List", "portList", "portMaskList",
                "macAddressList", "countryList", "domainName", "domainNamePort")
_DOCUMENTED_FIELDS = (*_STRING_FIELDS, *_INT32_FIELDS, *_BOOL_FIELDS, *_LIST_FIELDS)
_MISSING = object()


class SiteGroupProfilesCoverageError(ValueError):
    """Raised when the fixed list response exceeds its accepted shape."""


def _coverage() -> dict[str, int]:
    return {"present": 0, "type_valid": 0, "missing": 0, "invalid": 0}


def _valid(field: str, value: object) -> bool:
    if field in _STRING_FIELDS:
        return isinstance(value, str)
    if field in _INT32_FIELDS:
        return type(value) is int and _INT32_MIN <= value <= _INT32_MAX
    if field in _BOOL_FIELDS:
        return type(value) is bool
    if field in _LIST_FIELDS:
        return isinstance(value, list)
    return False


def project_site_group_profiles_coverage(raw_result: object) -> dict[str, Any]:
    """Count documented field presence/types without returning values or list items."""
    if raw_result is _MISSING:
        return {
            "source_state": "missing", "row_count": None, "inspected_row_count": 0,
            "omitted_row_count": 0, "valid_row_count": 0, "invalid_row_count": 0,
            "field_coverage": {field: _coverage() for field in _DOCUMENTED_FIELDS},
            "unknown_field_count": 0, "partial": True,
            "identifiers_labels_values_and_list_elements_returned": False,
        }
    if not isinstance(raw_result, list):
        raise SiteGroupProfilesCoverageError("response_invalid")
    if len(raw_result) > 100_000:
        raise SiteGroupProfilesCoverageError("response_invalid")

    inspected = raw_result[:MAX_GROUP_PROFILE_ROWS]
    coverage = {field: _coverage() for field in _DOCUMENTED_FIELDS}
    valid_rows = invalid_rows = unknown_field_count = 0
    for row in inspected:
        if not isinstance(row, Mapping) or len(row) > _MAX_FIELDS:
            invalid_rows += 1
            continue
        valid_rows += 1
        unknown_field_count += sum(key not in _DOCUMENTED_FIELDS for key in row)
        for field in _DOCUMENTED_FIELDS:
            value = row.get(field, _MISSING)
            item = coverage[field]
            if value is _MISSING:
                item["missing"] += 1
            else:
                item["present"] += 1
                if _valid(field, value):
                    item["type_valid"] += 1
                else:
                    item["invalid"] += 1

    omitted = len(raw_result) - len(inspected)
    missing_count = sum(item["missing"] for item in coverage.values())
    invalid_field_count = sum(item["invalid"] for item in coverage.values())
    return {
        "source_state": "empty" if not raw_result else "nonempty",
        "row_count": len(raw_result),
        "inspected_row_count": len(inspected),
        "omitted_row_count": omitted,
        "valid_row_count": valid_rows,
        "invalid_row_count": invalid_rows,
        "field_coverage": coverage,
        "missing_field_count": missing_count,
        "invalid_field_count": invalid_field_count,
        "unknown_field_count": unknown_field_count,
        "partial": bool(omitted or invalid_rows or missing_count or invalid_field_count or
                         unknown_field_count),
        "identifiers_labels_values_and_list_elements_returned": False,
    }


MISSING_GROUP_PROFILES_RESULT = _MISSING
