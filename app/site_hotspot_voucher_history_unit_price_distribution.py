"""Redacted field coverage for the fixed voucher unit-price distribution read."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_VOUCHER_UNIT_PRICE_DISTRIBUTION_ROWS = 500
_INT32_MIN, _INT32_MAX = -(1 << 31), (1 << 31) - 1
_GRID_FIELDS = ("totalRows", "currentPage", "currentSize", "data")
_ROW_FIELDS = ("unitPrice", "totalAmount", "currency", "usedCount")
_ROW_TYPES = {"unitPrice": "string", "totalAmount": "string", "currency": "string", "usedCount": "int32"}
_MISSING = object()
MISSING_VOUCHER_UNIT_PRICE_DISTRIBUTION_RESULT = _MISSING


class VoucherUnitPriceDistributionError(ValueError):
    """Raised when the bounded documented Grid response is malformed."""


def _counter() -> dict[str, int]:
    return {"present": 0, "type_valid": 0, "missing": 0, "null": 0, "invalid": 0}


def _coverage(fields: tuple[str, ...]) -> dict[str, dict[str, int]]:
    return {name: _counter() for name in fields}


def _empty(state: str) -> dict[str, object]:
    return {"source_state": state, "grid_field_coverage": _coverage(_GRID_FIELDS),
            "row_count": None, "row_field_coverage": _coverage(_ROW_FIELDS),
            "invalid_row_count": 0, "unknown_field_count": 0, "partial": True,
            "server_completeness": "not_asserted"}


def project_voucher_unit_price_distribution(result: Any) -> dict[str, object]:
    """Return only field presence/type counts; never return price or currency values."""
    if result is _MISSING:
        return _empty("result_missing")
    if result is None:
        return _empty("result_null")
    if not isinstance(result, Mapping) or len(result) > 16 or any(not isinstance(k, str) for k in result):
        raise VoucherUnitPriceDistributionError("grid_invalid")
    unknown = sum(k not in _GRID_FIELDS for k in result)
    grid = _coverage(_GRID_FIELDS)
    valid_grid: dict[str, bool] = {}
    for key in _GRID_FIELDS:
        c = grid[key]
        if key not in result:
            c["missing"] = 1
            valid_grid[key] = False
            continue
        c["present"] = 1
        value = result[key]
        if value is None:
            c["null"] = 1
            valid_grid[key] = False
            continue
        if key == "data":
            valid = isinstance(value, list)
        elif key == "totalRows":
            valid = type(value) is int and -(1 << 63) <= value <= (1 << 63) - 1
        else:
            valid = type(value) is int and 0 <= value <= _INT32_MAX
        c["type_valid"] = int(valid)
        c["invalid"] = int(not valid)
        valid_grid[key] = valid
    data = result.get("data", _MISSING)
    rows = data if isinstance(data, list) else []
    if len(rows) > MAX_VOUCHER_UNIT_PRICE_DISTRIBUTION_ROWS:
        raise VoucherUnitPriceDistributionError("rows_over_limit")
    row_cov = _coverage(_ROW_FIELDS)
    invalid_rows = 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 32 or any(not isinstance(k, str) for k in row):
            invalid_rows += 1
            continue
        unknown += sum(k not in _ROW_FIELDS for k in row)
        for key in _ROW_FIELDS:
            c = row_cov[key]
            if key not in row:
                c["missing"] += 1
                continue
            c["present"] += 1
            value = row[key]
            if value is None:
                c["null"] += 1
                continue
            valid = isinstance(value, str) if _ROW_TYPES[key] == "string" else (
                type(value) is int and _INT32_MIN <= value <= _INT32_MAX)
            c["type_valid"] += int(valid)
            c["invalid"] += int(not valid)
    partial = bool(invalid_rows or unknown or any(
        c["missing"] or c["null"] or c["invalid"] for group in (grid, row_cov) for c in group.values()))
    return {"source_state": "grid", "grid_field_coverage": grid,
            "row_count": len(rows) if valid_grid.get("data") else None,
            "row_field_coverage": row_cov, "invalid_row_count": invalid_rows,
            "unknown_field_count": unknown, "partial": partial,
            "server_completeness": "not_asserted"}
