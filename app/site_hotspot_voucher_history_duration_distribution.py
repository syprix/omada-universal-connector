"""Redacted field coverage for the fixed voucher-duration distribution read."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_VOUCHER_DURATION_DISTRIBUTION_ROWS = 500
_INT32_MIN, _INT32_MAX = -(1 << 31), (1 << 31) - 1
_INT64_MIN, _INT64_MAX = -(1 << 63), (1 << 63) - 1
_GRID_FIELDS = ("totalRows", "currentPage", "currentSize", "data")
_ROW_FIELDS = ("duration", "durationType", "totalDuration", "usedCount")
_ROW_TYPES = {"duration": "int64", "durationType": "int32",
              "totalDuration": "int64", "usedCount": "int32"}
_MISSING = object()
MISSING_VOUCHER_DURATION_DISTRIBUTION_RESULT = _MISSING


class VoucherDurationDistributionError(ValueError):
    """Raised when the bounded documented Grid response is malformed."""


def _counter() -> dict[str, int]:
    return {"present": 0, "type_valid": 0, "missing": 0, "null": 0,
            "invalid": 0, "zero_count": 0}


def _state_coverage(fields: tuple[str, ...]) -> dict[str, dict[str, int]]:
    return {name: _counter() for name in fields}


def _integer(value: Any, bits: int) -> bool:
    if type(value) is not int:
        return False
    low, high = (_INT32_MIN, _INT32_MAX) if bits == 32 else (_INT64_MIN, _INT64_MAX)
    return low <= value <= high


def _empty(state: str) -> dict[str, object]:
    return {
        "source_state": state,
        "grid_field_coverage": _state_coverage(_GRID_FIELDS),
        "row_count": None,
        "row_field_coverage": _state_coverage(_ROW_FIELDS),
        "invalid_row_count": 0,
        "unknown_field_count": 0,
        "partial": True,
        "server_completeness": "not_asserted",
    }


def project_voucher_duration_distribution(result: Any) -> dict[str, object]:
    """Project only bounded schema/presence counts, never distribution values."""
    if result is _MISSING:
        return _empty("result_missing")
    if result is None:
        return _empty("result_null")
    if (not isinstance(result, Mapping) or len(result) > 16 or
            any(not isinstance(key, str) for key in result)):
        raise VoucherDurationDistributionError("grid_invalid")

    unknown_fields = sum(key not in _GRID_FIELDS for key in result)
    grid_coverage = _state_coverage(_GRID_FIELDS)
    valid_grid: dict[str, bool] = {}
    for key in _GRID_FIELDS:
        counter = grid_coverage[key]
        if key not in result:
            counter["missing"] = 1
            valid_grid[key] = False
            continue
        counter["present"] = 1
        value = result[key]
        if value is None:
            counter["null"] = 1
            valid_grid[key] = False
            continue
        if key == "data":
            valid = isinstance(value, list)
        elif key == "totalRows":
            valid = _integer(value, 64)
        else:
            valid = _integer(value, 32)
        counter["type_valid"] = int(valid)
        counter["invalid"] = int(not valid)
        if valid and type(value) is int:
            counter["zero_count"] = int(value == 0)
        valid_grid[key] = valid

    data = result.get("data", _MISSING)
    rows = data if isinstance(data, list) else []
    if len(rows) > MAX_VOUCHER_DURATION_DISTRIBUTION_ROWS:
        raise VoucherDurationDistributionError("rows_over_limit")

    row_coverage = _state_coverage(_ROW_FIELDS)
    invalid_rows = 0
    for row in rows:
        if (not isinstance(row, Mapping) or len(row) > 32 or
                any(not isinstance(key, str) for key in row)):
            invalid_rows += 1
            continue
        unknown_fields += sum(key not in _ROW_FIELDS for key in row)
        for key in _ROW_FIELDS:
            counts = row_coverage[key]
            if key not in row:
                counts["missing"] += 1
                continue
            counts["present"] += 1
            value = row[key]
            if value is None:
                counts["null"] += 1
                continue
            bits = 32 if _ROW_TYPES[key] == "int32" else 64
            valid = _integer(value, bits)
            if key == "durationType":
                valid = valid and value in (0, 1)
            counts["type_valid"] += int(valid)
            counts["invalid"] += int(not valid)
            if valid:
                counts["zero_count"] += int(value == 0)

    row_count = len(rows) if valid_grid.get("data", False) else None
    partial = bool(
        any(counts["missing"] or counts["null"] or counts["invalid"]
            for counts in grid_coverage.values()) or
        any(counts["missing"] or counts["null"] or counts["invalid"]
            for counts in row_coverage.values()) or invalid_rows or unknown_fields
    )
    return {
        "source_state": "grid",
        "grid_field_coverage": grid_coverage,
        "row_count": row_count,
        "row_field_coverage": row_coverage,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "server_completeness": "not_asserted",
    }
