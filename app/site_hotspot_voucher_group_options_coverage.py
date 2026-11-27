"""Redacted first-page shape coverage for voucher-group options."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_VOUCHER_GROUP_OPTIONS_PAGE_SIZE = 100
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1
_RESULT_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_OPTION_FIELDS = ("groupId", "name")
_MISSING = object()
MISSING_VOUCHER_GROUP_OPTIONS_RESULT = _MISSING


class SiteHotspotVoucherGroupOptionsCoverageError(ValueError):
    """Raised when the documented first-page shape is malformed or over bound."""


def _field(present: bool, valid: bool = False) -> dict[str, int]:
    return {"present": int(present), "type_valid": int(present and valid),
            "missing": int(not present), "invalid": int(present and not valid)}


def _empty_group_field_coverage() -> dict[str, dict[str, int]]:
    # These counters describe returned option rows.  An empty page has no
    # missing row fields; absent page metadata is reported separately.
    return {key: {"present": 0, "type_valid": 0, "missing": 0, "invalid": 0}
            for key in _OPTION_FIELDS}


def _empty(page_size: int, source_state: str) -> dict[str, object]:
    return {
        "source_state": source_state,
        "page_number": 1,
        "page_size": page_size,
        "page_state": "metadata_missing",
        "reported_total_row_count": None,
        "returned_row_count": None,
        "reported_remaining_row_count": None,
        "first_page_covers_reported_total": None,
        "pagination_field_coverage": {
            key: _field(False) for key in ("totalRows", "currentPage", "currentSize", "data")},
        "group_field_coverage": _empty_group_field_coverage(),
        "invalid_row_count": 0,
        "unknown_field_count": 0,
        "partial": True,
        "voucher_group_values_returned": False,
    }


def project_site_hotspot_voucher_group_options_coverage(
        result: Any, *, page_size: int = MAX_VOUCHER_GROUP_OPTIONS_PAGE_SIZE) -> dict[str, object]:
    """Report only page metadata and field-shape counts; never return option values."""
    if type(page_size) is not int or not 1 <= page_size <= MAX_VOUCHER_GROUP_OPTIONS_PAGE_SIZE:
        raise SiteHotspotVoucherGroupOptionsCoverageError("page_size_invalid")
    if result is _MISSING:
        return _empty(page_size, "result_missing")
    if not isinstance(result, Mapping) or len(result) > 12 or any(not isinstance(k, str) for k in result):
        raise SiteHotspotVoucherGroupOptionsCoverageError("result_invalid")

    total = result.get("totalRows", _MISSING)
    current_page = result.get("currentPage", _MISSING)
    current_size = result.get("currentSize", _MISSING)
    data = result.get("data", _MISSING)
    pagination_values = {"totalRows": total, "currentPage": current_page,
                         "currentSize": current_size, "data": data}
    pagination: dict[str, dict[str, int]] = {}
    for key, value in pagination_values.items():
        if value is _MISSING:
            pagination[key] = _field(False)
            continue
        valid = (type(value) is int and 0 <= value <= _INT64_MAX if key == "totalRows" else
                 type(value) is int and 0 <= value <= _INT32_MAX if key in {"currentPage", "currentSize"} else
                 isinstance(value, list))
        pagination[key] = _field(True, valid)
    if any(item["invalid"] for item in pagination.values()):
        raise SiteHotspotVoucherGroupOptionsCoverageError("pagination_invalid")
    if data is not _MISSING and len(data) > page_size:
        raise SiteHotspotVoucherGroupOptionsCoverageError("data_invalid")

    if data is _MISSING:
        rows: list[Any] = []
        count: int | None = None
        source_state = "data_missing"
    else:
        rows = data
        count = len(rows)
        source_state = ("empty_total_unknown" if count == 0 else "nonempty_total_unknown") if total is _MISSING else None

    total_value = total if type(total) is int else None
    empty_zero_page = (total_value == 0 and data == [] and current_page == 0 and current_size == 0)
    if current_page is not _MISSING and current_page != 1 and not empty_zero_page:
        raise SiteHotspotVoucherGroupOptionsCoverageError("page_number_inconsistent")
    if (current_size is not _MISSING and data is not _MISSING and
            current_size not in (count, page_size) and
            not (total_value == 0 and count == 0 and current_size == 0)):
        raise SiteHotspotVoucherGroupOptionsCoverageError("page_size_inconsistent")

    inconsistent_first_page_total = (
        total_value is not None and count is not None and count > total_value)
    if (total_value is not None and count is not None and
            (inconsistent_first_page_total or (total_value > 0 and count == 0))):
        valid_documented_rows = (
            data is not _MISSING and current_page == 1 and
            current_size is not _MISSING and
            current_size in (count, page_size) and
            all(isinstance(row, Mapping) and len(row) <= 16 and
                all(isinstance(key, str) for key in row) and
                all(key in row and isinstance(row[key], str) for key in _OPTION_FIELDS)
                for row in rows))
        if not (inconsistent_first_page_total and valid_documented_rows):
            raise SiteHotspotVoucherGroupOptionsCoverageError("total_rows_inconsistent")

    coverage = _empty_group_field_coverage()
    invalid_rows = 0
    unknown_fields = sum(key not in _RESULT_FIELDS for key in result)
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 16 or any(not isinstance(key, str) for key in row):
            invalid_rows += 1
            continue
        unknown_fields += sum(key not in _OPTION_FIELDS for key in row)
        for key in _OPTION_FIELDS:
            if key not in row:
                coverage[key]["missing"] += 1
            else:
                coverage[key]["present"] += 1
                valid = isinstance(row[key], str)
                coverage[key]["type_valid"] += int(valid)
                coverage[key]["invalid"] += int(not valid)

    covers_total = count == total_value if count is not None and total_value is not None else None
    remaining = max(total_value - count, 0) if count is not None and total_value is not None else None
    if total_value == 0 and count == 0:
        page_state = "empty"
    elif inconsistent_first_page_total:
        page_state = "first_page_inconsistent_total"
        covers_total = None
        remaining = None
    elif total_value is None:
        page_state = "metadata_missing" if data is _MISSING else (
            "empty_total_unknown" if count == 0 else "nonempty_total_unknown")
    elif count is None:
        page_state = "data_missing"
    elif count < total_value:
        page_state = "first_page_partial"
    else:
        page_state = "first_page_complete"
    partial = bool(inconsistent_first_page_total or
                   any(item["missing"] for item in pagination.values()) or
                   invalid_rows or unknown_fields or
                   any(counts["missing"] or counts["invalid"] for counts in coverage.values()) or
                   covers_total is not True)
    if source_state is None:
        source_state = "empty" if page_state == "empty" else (
            "first_page" if page_state.startswith("first_page") else page_state)
    return {
        "source_state": source_state,
        "page_number": 1,
        "page_size": page_size,
        "page_state": page_state,
        "reported_total_row_count": total_value,
        "returned_row_count": count,
        "reported_remaining_row_count": remaining,
        "first_page_covers_reported_total": covers_total,
        "pagination_field_coverage": pagination,
        "group_field_coverage": coverage,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "voucher_group_values_returned": False,
    }
