"""Redacted first-page coverage for the documented voucher-group inventory."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_SITE_VOUCHER_GROUP_PAGE_SIZE = 100
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1
_PAGINATION_FIELDS = ("totalRows", "currentPage", "currentSize", "data")
_COUNT_FIELDS = ("unusedCount", "usedCount", "inUseCount", "expiredCount", "totalCount")
# Names come from VoucherGroupOpenApiVO in all three supplied source exports.
# Values for fields outside _COUNT_FIELDS are never read.
_DOCUMENTED_ROW_FIELDS = frozenset((
    "id", "name", "createdTime", "creatorName", "limitType", "limitNum",
    "durationType", "duration", "timingType", "rateLimit", "trafficLimitEnable",
    "trafficLimit", "trafficLimitFrequency", "unitPrice", "currency", "portalNames",
    "applyToAllPortals", "expirationTime", "effectiveTime", "validityType", "schedule",
    "logout", "description", "printComments", "unusedCount", "usedCount", "inUseCount",
    "expiredCount", "totalCount", "totalAmount",
))
_MISSING = object()
MISSING_SITE_VOUCHER_GROUP_RESULT = _MISSING


class SiteVoucherGroupInventoryCoverageError(ValueError):
    """Raised when the documented first-page response is malformed or over bound."""


def _field(present: bool, valid: bool = False) -> dict[str, int]:
    return {"present": int(present), "type_valid": int(present and valid),
            "missing": int(not present), "invalid": int(present and not valid)}


def _empty_field_coverage() -> dict[str, dict[str, int]]:
    return {key: {"present": 0, "type_valid": 0, "missing": 0, "invalid": 0}
            for key in _COUNT_FIELDS}


def _empty(page_size: int, state: str) -> dict[str, object]:
    return {
        "source_state": state,
        "page_number": 1,
        "page_size": page_size,
        "page_state": "metadata_missing",
        "reported_total_row_count": None,
        "returned_row_count": None,
        "reported_remaining_row_count": None,
        "first_page_covers_reported_total": None,
        "pagination_field_coverage": {key: _field(False) for key in _PAGINATION_FIELDS},
        "voucher_count_field_coverage": _empty_field_coverage(),
        "invalid_row_count": 0,
        "unknown_field_count": 0,
        "partial": True,
        "voucher_group_values_returned": False,
    }


def project_site_voucher_group_inventory_coverage(
        result: Any, *, page_size: int = MAX_SITE_VOUCHER_GROUP_PAGE_SIZE) -> dict[str, object]:
    """Return bounded paging and documented counter-field coverage, never source values."""
    if type(page_size) is not int or not 1 <= page_size <= MAX_SITE_VOUCHER_GROUP_PAGE_SIZE:
        raise SiteVoucherGroupInventoryCoverageError("page_size_invalid")
    if result is _MISSING:
        return _empty(page_size, "result_missing")
    if not isinstance(result, Mapping) or len(result) > 12 or any(not isinstance(k, str) for k in result):
        raise SiteVoucherGroupInventoryCoverageError("result_invalid")

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
                 type(value) is int and 0 <= value <= _INT32_MAX
                 if key in {"currentPage", "currentSize"} else isinstance(value, list))
        pagination[key] = _field(True, valid)
    if any(item["invalid"] for item in pagination.values()):
        raise SiteVoucherGroupInventoryCoverageError("pagination_invalid")

    if data is _MISSING:
        rows: list[Any] = []
        count: int | None = None
    else:
        rows = data
        count = len(rows)
        if count > page_size:
            raise SiteVoucherGroupInventoryCoverageError("data_over_page_limit")

    total_value = total if type(total) is int else None
    if current_page is not _MISSING and current_page != 1:
        raise SiteVoucherGroupInventoryCoverageError("page_number_inconsistent")
    if (current_size is not _MISSING and data is not _MISSING and
            current_size not in (count, page_size)):
        raise SiteVoucherGroupInventoryCoverageError("page_size_inconsistent")

    # The grid contract requires the reported total to cover its returned first page.
    # Do not inherit the options reader's special handling for rows > totalRows.
    if total_value is not None and count is not None:
        if count > total_value or (total_value > 0 and count == 0):
            raise SiteVoucherGroupInventoryCoverageError("total_rows_inconsistent")

    coverage = _empty_field_coverage()
    invalid_rows = 0
    unknown_fields = sum(key not in _PAGINATION_FIELDS for key in result)
    for row in rows:
        if (not isinstance(row, Mapping) or len(row) > 64 or
                any(not isinstance(key, str) for key in row)):
            invalid_rows += 1
            continue
        unknown_fields += sum(key not in _DOCUMENTED_ROW_FIELDS for key in row)
        for key in _COUNT_FIELDS:
            if key not in row:
                coverage[key]["missing"] += 1
                continue
            coverage[key]["present"] += 1
            value = row[key]
            valid = type(value) is int and 0 <= value <= _INT32_MAX
            coverage[key]["type_valid"] += int(valid)
            coverage[key]["invalid"] += int(not valid)

    if data is _MISSING:
        page_state = "data_missing"
        source_state = "data_missing"
    elif total_value is None:
        page_state = "total_unknown"
        source_state = "empty_total_unknown" if count == 0 else "nonempty_total_unknown"
    elif total_value == 0 and count == 0:
        page_state = "empty"
        source_state = "empty"
    elif count < total_value:
        page_state = "first_page_partial"
        source_state = "first_page"
    else:
        page_state = "first_page_complete"
        source_state = "first_page"

    covers_total = (count == total_value) if count is not None and total_value is not None else None
    remaining = max(total_value - count, 0) if count is not None and total_value is not None else None
    partial = bool(
        any(value["missing"] or value["invalid"] for value in pagination.values()) or
        invalid_rows or unknown_fields or
        any(value["missing"] or value["invalid"] for value in coverage.values()) or
        covers_total is not True
    )
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
        "voucher_count_field_coverage": coverage,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "voucher_group_values_returned": False,
    }
