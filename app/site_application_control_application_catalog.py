"""First-page, redacted coverage for the site application-control catalog."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

MAX_APPLICATION_CATALOG_PAGE_SIZE = 100
_INT32_MIN = -(1 << 31)
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1
_RESULT_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_ROW_FIELDS = frozenset(("applicationId", "applicationName", "description", "family"))
MISSING_APPLICATION_CATALOG_RESULT = object()
_MISSING = MISSING_APPLICATION_CATALOG_RESULT


class SiteApplicationControlApplicationCatalogError(ValueError):
    """Raised when the documented first-page shape is invalid or over bound."""


def _field(present: bool, valid: bool = False) -> dict[str, int]:
    return {"present": int(present), "type_valid": int(present and valid),
            "missing": int(not present), "invalid": int(present and not valid)}


def _pagination(total: object = _MISSING, page: object = _MISSING,
                size: object = _MISSING, data: object = _MISSING) -> dict[str, dict[str, int]]:
    values = {"totalRows": total, "currentPage": page, "currentSize": size, "data": data}
    result: dict[str, dict[str, int]] = {}
    for key, value in values.items():
        if value is _MISSING:
            result[key] = _field(False)
        else:
            valid = (type(value) is int and 0 <= value <= _INT64_MAX if key == "totalRows" else
                     type(value) is int and 0 <= value <= (1 << 31) - 1 if key in {"currentPage", "currentSize"} else
                     isinstance(value, list))
            result[key] = _field(True, valid)
    return result


def _empty_result(*, page_size: int, source_state: str) -> dict[str, object]:
    missing = {name: _field(False) for name in ("totalRows", "currentPage", "currentSize", "data")}
    return {
        "source_state": source_state,
        "page_number": 1,
        "page_size": page_size,
        "page_state": "metadata_missing",
        "reported_total_row_count": None,
        "returned_row_count": None,
        "reported_remaining_row_count": None,
        "first_page_covers_reported_total": None,
        "pagination_field_coverage": missing,
        "application_id_coverage": _field_counts(),
        "unique_application_id_count": 0,
        "duplicate_application_id_count": 0,
        "invalid_row_count": 0,
        "unknown_field_count": 0,
        "partial": True,
        "application_identifiers_and_labels_returned": False,
    }


def _field_counts() -> dict[str, int]:
    return {"present": 0, "type_valid": 0, "missing": 0, "invalid": 0}


def project_site_application_control_application_catalog(
        result: Any, *, page_size: int = MAX_APPLICATION_CATALOG_PAGE_SIZE) -> dict[str, object]:
    """Project only first-page counts and applicationId type coverage, never values."""
    if type(page_size) is not int or not 1 <= page_size <= MAX_APPLICATION_CATALOG_PAGE_SIZE:
        raise SiteApplicationControlApplicationCatalogError("page_size_invalid")
    if result is _MISSING:
        return _empty_result(page_size=page_size, source_state="result_missing")
    if not isinstance(result, Mapping) or len(result) > 12 or any(not isinstance(k, str) for k in result):
        raise SiteApplicationControlApplicationCatalogError("result_invalid")

    total = result.get("totalRows", _MISSING)
    current_page = result.get("currentPage", _MISSING)
    current_size = result.get("currentSize", _MISSING)
    data = result.get("data", _MISSING)
    pagination = _pagination(total, current_page, current_size, data)
    if any(item["invalid"] for item in pagination.values()):
        raise SiteApplicationControlApplicationCatalogError("pagination_invalid")
    if data is not _MISSING and (not isinstance(data, list) or len(data) > page_size):
        raise SiteApplicationControlApplicationCatalogError("data_invalid")

    if data is _MISSING:
        count: int | None = None
        rows: list[Any] = []
        source_state = "data_missing"
    else:
        rows = data
        count = len(rows)
        source_state = "empty_total_unknown" if count == 0 and total is _MISSING else (
            "nonempty_total_unknown" if count and total is _MISSING else None)

    empty_zero_based = (total == 0 and data == [] and current_page == 0 and current_size == 0)
    if (total is not _MISSING and data is not _MISSING and count is not None and
            ((count > total) or (total > 0 and count == 0))):
        raise SiteApplicationControlApplicationCatalogError("total_rows_inconsistent")
    if current_page is not _MISSING and current_page != 1 and not empty_zero_based:
        raise SiteApplicationControlApplicationCatalogError("page_number_inconsistent")
    if (current_size is not _MISSING and data is not _MISSING and
            current_size not in (count, page_size) and not (total == 0 and count == 0 and current_size == 0)):
        raise SiteApplicationControlApplicationCatalogError("page_size_inconsistent")

    ids = _field_counts()
    valid_ids: list[int] = []
    invalid_rows = 0
    unknown_fields = sum(key not in _RESULT_FIELDS for key in result)
    for row in rows:
        if (not isinstance(row, Mapping) or len(row) > 16 or
                any(not isinstance(key, str) for key in row)):
            invalid_rows += 1
            continue
        unknown_fields += sum(key not in _ROW_FIELDS for key in row)
        if "applicationId" not in row:
            ids["missing"] += 1
            continue
        ids["present"] += 1
        value = row["applicationId"]
        if type(value) is int and _INT32_MIN <= value <= _INT32_MAX:
            ids["type_valid"] += 1
            valid_ids.append(value)
        else:
            ids["invalid"] += 1
    frequencies = Counter(valid_ids)
    duplicates = sum(number - 1 for number in frequencies.values() if number > 1)
    unique_count = len(frequencies)

    total_value = total if type(total) is int else None
    first_page_covers = (count == total_value) if count is not None and total_value is not None else None
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
        any(item["missing"] for item in pagination.values()) or invalid_rows or
        ids["missing"] or ids["invalid"] or unknown_fields or duplicates or
        first_page_covers is not True)
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
        "first_page_covers_reported_total": first_page_covers,
        "pagination_field_coverage": pagination,
        "application_id_coverage": ids,
        "unique_application_id_count": unique_count,
        "duplicate_application_id_count": duplicates,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "application_identifiers_and_labels_returned": False,
    }
