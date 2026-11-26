"""Redacted first-page coverage for the controller-wide unplaced-site list."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PAGE_SIZE = 100
MAX_ENVELOPE_FIELDS = 12
MAX_ROW_FIELDS = 16
MAX_STRING_LENGTH = 4096
MAX_INT32 = (1 << 31) - 1
MIN_INT32 = -(1 << 31)
MAX_INT64 = (1 << 63) - 1
_RESULT_FIELDS = frozenset({"totalRows", "currentPage", "currentSize", "data", "unplacedNum"})
_ROW_FIELD_TYPES = {"id": "string", "region": "string", "name": "string", "type": "int32"}


class ControllerUnplacedSitePositionError(ValueError):
    """Raised when the bounded documented page is structurally invalid."""


def _coverage() -> dict[str, int]:
    return {"present": 0, "type_valid": 0, "missing": 0, "invalid": 0}


def _counter_state(result: Mapping[str, Any], field: str) -> tuple[str, int | None]:
    if field not in result:
        return "not_reported", None
    value = result[field]
    if type(value) is not int or not 0 <= value <= MAX_INT64:
        raise ControllerUnplacedSitePositionError("response_invalid")
    return "reported", value


def project_unplaced_site_positions(result: Any, *, page_size: int = PAGE_SIZE) -> dict[str, object]:
    """Summarize one validated page without returning site values or identities."""
    if (type(page_size) is not int or page_size != PAGE_SIZE or
            not isinstance(result, Mapping) or len(result) > MAX_ENVELOPE_FIELDS):
        raise ControllerUnplacedSitePositionError("response_invalid")

    rows = result.get("data")
    current_page = result.get("currentPage")
    current_size = result.get("currentSize")
    if (not isinstance(rows, list) or len(rows) > page_size or
            type(current_page) is not int or current_page != 1 or
            type(current_size) is not int or current_size not in (len(rows), page_size)):
        raise ControllerUnplacedSitePositionError("response_invalid")

    total_state, total_rows = _counter_state(result, "totalRows")
    unplaced_state, unplaced_num = _counter_state(result, "unplacedNum")
    if total_rows is not None and (total_rows < len(rows) or (not rows and total_rows != 0)):
        raise ControllerUnplacedSitePositionError("response_invalid")

    unknown_envelope_fields = sum(key not in _RESULT_FIELDS for key in result)
    field_coverage = {field: _coverage() for field in _ROW_FIELD_TYPES}
    invalid_row_count = unknown_field_count = 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > MAX_ROW_FIELDS:
            invalid_row_count += 1
            continue
        unknown_field_count += sum(key not in _ROW_FIELD_TYPES for key in row)
        for field, expected_type in _ROW_FIELD_TYPES.items():
            coverage = field_coverage[field]
            if field not in row:
                coverage["missing"] += 1
                continue
            coverage["present"] += 1
            value = row[field]
            if expected_type == "string":
                valid = isinstance(value, str) and len(value) <= MAX_STRING_LENGTH
            else:
                valid = type(value) is int and MIN_INT32 <= value <= MAX_INT32
            coverage["type_valid" if valid else "invalid"] += 1

    missing_field_count = sum(item["missing"] for item in field_coverage.values())
    invalid_field_count = sum(item["invalid"] for item in field_coverage.values())
    page_truncated = total_rows is not None and total_rows > len(rows)
    page_coverage_state = ("unknown_total" if total_rows is None else
                           "truncated" if page_truncated else "complete_as_reported")
    state = "empty" if not rows else "present"
    partial = bool(page_truncated or total_rows is None or unplaced_num is None or
                   unknown_envelope_fields or invalid_row_count or unknown_field_count or
                   missing_field_count or invalid_field_count)
    return {
        "source_state": state,
        "returned_count": len(rows),
        "total_rows_state": total_state,
        "reported_total_rows": total_rows,
        "unplaced_num_state": unplaced_state,
        "reported_unplaced_num": unplaced_num,
        "omitted_count": total_rows - len(rows) if total_rows is not None else None,
        "page_truncated": page_truncated,
        "page_coverage_state": page_coverage_state,
        "documented_field_coverage": field_coverage,
        "unknown_envelope_field_count": unknown_envelope_fields,
        "unknown_row_field_count": unknown_field_count,
        "invalid_row_count": invalid_row_count,
        "missing_field_count": missing_field_count,
        "invalid_field_count": invalid_field_count,
        "partial": partial,
    }
