"""Redacted field coverage for one fixed site session-limit rule page."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SESSION_LIMIT_RULE_PAGE_SIZE = 100
_MAX_ROW_FIELDS = 32
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1
_STRING_FIELDS = ("id", "name", "ip")
_INT32_FIELDS = ("index", "sourceType", "maxSession")
_BOOL_FIELDS = ("status", "existIpAddress")
# The API exports for Hardware Controller and CBC include featureDescription;
# the ER7212PC export does not. Its absence is therefore tracked as optional.
_LIST_FIELDS = ("sourceIds", "featureDescription")
_FIELDS = (*_STRING_FIELDS, *_INT32_FIELDS, *_BOOL_FIELDS, *_LIST_FIELDS)
_REQUIRED_FIELDS = frozenset(("name", "status", "sourceType", "maxSession"))
_RESULT_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data",
                            "supportIpAddress"))
_MISSING = object()


class SiteSessionLimitRuleCoverageError(ValueError):
    """Raised when the fixed response or first page is structurally invalid."""


def _counter() -> dict[str, int]:
    return {"present": 0, "type_valid": 0, "missing": 0, "invalid": 0}


def _valid_type(field: str, value: object) -> bool:
    if field in _STRING_FIELDS:
        return isinstance(value, str)
    if field in _INT32_FIELDS:
        return type(value) is int and -(1 << 31) <= value <= _INT32_MAX
    if field in _BOOL_FIELDS or field == "supportIpAddress":
        return type(value) is bool
    if field in _LIST_FIELDS:
        # Deliberately validate only the array form; do not inspect entries.
        return isinstance(value, list)
    return False


def _empty_field_coverage() -> dict[str, dict[str, int]]:
    return {field: _counter() for field in _FIELDS}


def project_site_session_limit_rule_coverage(
        raw_result: object, *, page_size: int = SESSION_LIMIT_RULE_PAGE_SIZE) -> dict[str, Any]:
    """Return counts and documented shape only; never return or inspect rule values."""
    if type(page_size) is not int or not 1 <= page_size <= SESSION_LIMIT_RULE_PAGE_SIZE:
        raise SiteSessionLimitRuleCoverageError("response_invalid")

    support = _counter()
    if raw_result is _MISSING:
        support["missing"] = 1
        return {
            "source_state": "result_missing",
            "page_number": 1,
            "page_size": page_size,
            "page_state": "metadata_missing",
            "reported_total_row_count": None,
            "returned_row_count": None,
            "reported_remaining_row_count": None,
            "first_page_covers_reported_total": None,
            "pagination_field_coverage": {
                name: {"present": 0, "type_valid": 0, "missing": 1, "invalid": 0}
                for name in ("totalRows", "currentPage", "currentSize", "data")
            },
            "support_ip_address_coverage": support,
            "row_field_coverage": _empty_field_coverage(),
            "valid_row_count": 0,
            "invalid_row_count": 0,
            "required_field_missing_count": 0,
            "invalid_field_count": 0,
            "unknown_field_count": 0,
            "partial": True,
            "rule_values_identifiers_and_list_entries_returned": False,
        }
    if not isinstance(raw_result, Mapping) or len(raw_result) > _MAX_ROW_FIELDS + 8:
        raise SiteSessionLimitRuleCoverageError("response_invalid")

    unknown_field_count = sum(key not in _RESULT_FIELDS for key in raw_result)
    if any(not isinstance(key, str) for key in raw_result):
        raise SiteSessionLimitRuleCoverageError("response_invalid")
    field_coverage = _empty_field_coverage()
    pagination = {}
    for field in ("totalRows", "currentPage", "currentSize", "data"):
        counter = _counter()
        if field not in raw_result:
            counter["missing"] = 1
        else:
            counter["present"] = 1
            expected = raw_result[field]
            if field == "totalRows":
                valid = type(expected) is int and 0 <= expected <= _INT64_MAX
            elif field in ("currentPage", "currentSize"):
                valid = type(expected) is int and 0 <= expected <= _INT32_MAX
            else:
                valid = isinstance(expected, list)
            if valid:
                counter["type_valid"] = 1
            else:
                counter["invalid"] = 1
        pagination[field] = counter

    if "supportIpAddress" not in raw_result:
        support["missing"] = 1
    else:
        support["present"] = 1
        if _valid_type("supportIpAddress", raw_result["supportIpAddress"]):
            support["type_valid"] = 1
        else:
            support["invalid"] = 1

    if any(counter["invalid"] for counter in pagination.values()):
        raise SiteSessionLimitRuleCoverageError("response_invalid")

    data = raw_result.get("data", _MISSING)
    if data is _MISSING:
        return {
            "source_state": "data_missing",
            "page_number": 1,
            "page_size": page_size,
            "page_state": "metadata_missing" if any(
                pagination[name]["missing"] for name in ("totalRows", "currentPage", "currentSize")
            ) else "data_missing",
            "reported_total_row_count": raw_result.get("totalRows"),
            "returned_row_count": None,
            "reported_remaining_row_count": None,
            "first_page_covers_reported_total": None,
            "pagination_field_coverage": pagination,
            "support_ip_address_coverage": support,
            "row_field_coverage": field_coverage,
            "valid_row_count": 0,
            "invalid_row_count": 0,
            "required_field_missing_count": 0,
            "invalid_field_count": 0,
            "unknown_field_count": unknown_field_count,
            "partial": True,
            "rule_values_identifiers_and_list_entries_returned": False,
        }
    if len(data) > page_size:
        raise SiteSessionLimitRuleCoverageError("response_invalid")

    total = raw_result.get("totalRows", _MISSING)
    current_page = raw_result.get("currentPage", _MISSING)
    current_size = raw_result.get("currentSize", _MISSING)
    empty_zero_based_page = (total == 0 and not data and current_page == 0 and
                             current_size == 0)
    if ((total is not _MISSING and len(data) > total) or
            (total is not _MISSING and total > 0 and not data) or
            (current_page is not _MISSING and current_page != 1 and
             not empty_zero_based_page) or
            (current_size is not _MISSING and
             current_size not in (len(data), page_size) and
             not (total == 0 and not data and current_size == 0))):
        raise SiteSessionLimitRuleCoverageError("response_invalid")

    valid_rows = invalid_rows = required_missing = invalid_fields = 0
    for row in data:
        if (not isinstance(row, Mapping) or len(row) > _MAX_ROW_FIELDS or
                any(not isinstance(key, str) for key in row)):
            invalid_rows += 1
            continue
        valid_rows += 1
        unknown_field_count += sum(key not in _FIELDS for key in row)
        for field in _FIELDS:
            counter = field_coverage[field]
            if field not in row:
                counter["missing"] += 1
                if field in _REQUIRED_FIELDS:
                    required_missing += 1
                continue
            counter["present"] += 1
            if _valid_type(field, row[field]):
                counter["type_valid"] += 1
            else:
                counter["invalid"] += 1
                invalid_fields += 1

    metadata_missing = any(pagination[name]["missing"] for name in
                           ("totalRows", "currentPage", "currentSize"))
    page_state = "metadata_missing"
    remaining = None
    covers_total = None
    if not metadata_missing:
        if (current_page != 1 and not empty_zero_based_page or
                current_size not in (len(data), page_size) and
                not (total == 0 and not data and current_size == 0) or
                len(data) > total or (total > 0 and not data)):
            raise SiteSessionLimitRuleCoverageError("response_invalid")
        remaining = total - len(data)
        covers_total = remaining == 0
        page_state = "empty" if total == 0 else (
            "first_page_partial" if remaining else "first_page_covers_reported_total")

    missing_required_or_invalid = required_missing > 0 or invalid_fields > 0 or invalid_rows > 0
    partial = bool(metadata_missing or remaining not in (None, 0) or
                    missing_required_or_invalid or unknown_field_count or support["invalid"])
    return {
        "source_state": ("empty" if not data and total == 0 else
                         "empty_total_unknown" if not data else "nonempty"),
        "page_number": 1,
        "page_size": page_size,
        "page_state": page_state,
        "reported_total_row_count": None if total is _MISSING else total,
        "returned_row_count": len(data),
        "reported_remaining_row_count": remaining,
        "first_page_covers_reported_total": covers_total,
        "pagination_field_coverage": pagination,
        "support_ip_address_coverage": support,
        "row_field_coverage": field_coverage,
        "valid_row_count": valid_rows,
        "invalid_row_count": invalid_rows,
        "required_field_missing_count": required_missing,
        "optional_field_absent_count": sum(
            counter["missing"] for field, counter in field_coverage.items()
            if field not in _REQUIRED_FIELDS),
        "invalid_field_count": invalid_fields + support["invalid"],
        "unknown_field_count": unknown_field_count,
        "partial": partial,
        "rule_values_identifiers_and_list_entries_returned": False,
    }


MISSING_SESSION_LIMIT_RULE_RESULT = _MISSING
