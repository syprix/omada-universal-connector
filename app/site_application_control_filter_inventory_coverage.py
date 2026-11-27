"""Redacted first-page shape coverage for Application Control filters."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_FILTER_INVENTORY_PAGE_SIZE = 100
_INT32_MIN = -(1 << 31)
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1
_RESULT_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_FILTER_FIELDS = ("filterId", "filterName", "description", "rules")
_MISSING = object()
MISSING_FILTER_INVENTORY_RESULT = _MISSING


class SiteApplicationControlFilterInventoryError(ValueError):
    """Raised when the documented first-page shape is malformed or over bound."""


def _field_counts() -> dict[str, int]:
    return {"present": 0, "type_valid": 0, "missing": 0, "invalid": 0}


def _field(present: bool, valid: bool = False) -> dict[str, int]:
    return {"present": int(present), "type_valid": int(present and valid),
            "missing": int(not present), "invalid": int(present and not valid)}


def _pagination(total: object, page: object, size: object, data: object) -> dict[str, dict[str, int]]:
    values = {"totalRows": total, "currentPage": page, "currentSize": size, "data": data}
    result: dict[str, dict[str, int]] = {}
    for key, value in values.items():
        if value is _MISSING:
            result[key] = _field(False)
        else:
            valid = (type(value) is int and 0 <= value <= _INT64_MAX if key == "totalRows" else
                     type(value) is int and 0 <= value <= _INT32_MAX if key in {"currentPage", "currentSize"} else
                     isinstance(value, list))
            result[key] = _field(True, valid)
    return result


def _empty(*, page_size: int, source_state: str) -> dict[str, object]:
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
        "filter_field_coverage": {key: _field_counts() for key in _FILTER_FIELDS},
        "invalid_row_count": 0,
        "unknown_field_count": 0,
        "partial": True,
        "filter_values_and_rule_objects_returned": False,
    }


def project_site_application_control_filter_inventory_coverage(
        result: Any, *, page_size: int = MAX_FILTER_INVENTORY_PAGE_SIZE) -> dict[str, object]:
    """Return pagination and documented field-form counts without reading rule items."""
    if type(page_size) is not int or not 1 <= page_size <= MAX_FILTER_INVENTORY_PAGE_SIZE:
        raise SiteApplicationControlFilterInventoryError("page_size_invalid")
    if result is _MISSING:
        return _empty(page_size=page_size, source_state="result_missing")
    if not isinstance(result, Mapping) or len(result) > 12 or any(not isinstance(k, str) for k in result):
        raise SiteApplicationControlFilterInventoryError("result_invalid")

    total = result.get("totalRows", _MISSING)
    current_page = result.get("currentPage", _MISSING)
    current_size = result.get("currentSize", _MISSING)
    data = result.get("data", _MISSING)
    pagination = _pagination(total, current_page, current_size, data)
    if any(item["invalid"] for item in pagination.values()):
        raise SiteApplicationControlFilterInventoryError("pagination_invalid")
    if data is not _MISSING and (not isinstance(data, list) or len(data) > page_size):
        raise SiteApplicationControlFilterInventoryError("data_invalid")

    if data is _MISSING:
        rows: list[Any] = []
        count: int | None = None
        source_state = "data_missing"
    else:
        rows = data
        count = len(rows)
        source_state = ("empty_total_unknown" if count == 0 else "nonempty_total_unknown") if total is _MISSING else None

    empty_zero_page = (total == 0 and data == [] and current_page == 0 and current_size == 0)
    if (total is not _MISSING and data is not _MISSING and count is not None and
            (count > total or (total == 0 and count > 0) or (total > 0 and count == 0))):
        raise SiteApplicationControlFilterInventoryError("total_rows_inconsistent")
    if current_page is not _MISSING and current_page != 1 and not empty_zero_page:
        raise SiteApplicationControlFilterInventoryError("page_number_inconsistent")
    if (current_size is not _MISSING and data is not _MISSING and
            current_size not in (count, page_size) and not (total == 0 and count == 0 and current_size == 0)):
        raise SiteApplicationControlFilterInventoryError("page_size_inconsistent")

    coverage = {key: _field_counts() for key in _FILTER_FIELDS}
    invalid_rows = 0
    unknown_fields = sum(key not in _RESULT_FIELDS for key in result)
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 16 or any(not isinstance(key, str) for key in row):
            invalid_rows += 1
            continue
        unknown_fields += sum(key not in _FILTER_FIELDS for key in row)
        for key in _FILTER_FIELDS:
            if key not in row:
                coverage[key]["missing"] += 1
                continue
            coverage[key]["present"] += 1
            value = row[key]
            if key == "filterId":
                valid = type(value) is int and _INT32_MIN <= value <= _INT32_MAX
            elif key in {"filterName", "description"}:
                valid = isinstance(value, str)
            else:
                # The content of rules is sensitive and deliberately remains opaque.
                valid = isinstance(value, list)
            coverage[key]["type_valid"] += int(valid)
            coverage[key]["invalid"] += int(not valid)

    total_value = total if type(total) is int else None
    covers_total = count == total_value if count is not None and total_value is not None else None
    remaining = max(total_value - count, 0) if count is not None and total_value is not None else None
    if total_value == 0 and count == 0:
        page_state = "empty"
    elif total_value is None:
        page_state = "metadata_missing" if data is _MISSING else (
            "empty_total_unknown" if count == 0 else "nonempty_total_unknown")
    elif count is None:
        page_state = "data_missing"
    elif count < total_value:
        page_state = "first_page_partial"
    else:
        page_state = "first_page_complete"
    partial = bool(
        any(item["missing"] for item in pagination.values()) or invalid_rows or unknown_fields or
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
        "filter_field_coverage": coverage,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "filter_values_and_rule_objects_returned": False,
    }
