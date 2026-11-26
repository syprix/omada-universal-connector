"""Redacted first-page field coverage for site OUI profiles."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_PROFILE_ROWS = 100
_MAX_FIELDS = 16
_MAX_NESTED_ENTRIES = 512
_MAX_INT32 = (1 << 31) - 1
_MIN_INT32 = -(1 << 31)
_PROFILE_FIELDS = ("id", "name", "count", "ouiCombine")
_OUI_FIELDS = ("oui", "description")
_GRID_FIELDS = ("totalRows", "currentPage", "currentSize", "data", "totalCount")
_MISSING = object()


class SiteOuiProfileListError(ValueError):
    """Raised when the documented profile grid is outside its bounded shape."""


def _coverage() -> dict[str, int]:
    return {"present": 0, "type_valid": 0, "missing": 0, "invalid": 0}


def _valid(name: str, value: object) -> bool:
    if name == "totalRows":
        return type(value) is int and 0 <= value <= (1 << 63) - 1
    if name == "currentPage":
        return type(value) is int and 1 <= value <= _MAX_INT32
    if name == "currentSize":
        return type(value) is int and 0 <= value <= _MAX_INT32
    if name == "totalCount":
        return type(value) is int and -(1 << 31) <= value <= _MAX_INT32
    if name == "data":
        return isinstance(value, list) and len(value) <= MAX_PROFILE_ROWS
    if name in {"id", "oui"}:
        return isinstance(value, str)
    if name == "name":
        return isinstance(value, str) and 1 <= len(value) <= 64
    if name == "description":
        return isinstance(value, str) and len(value) <= 128
    if name == "count":
        return type(value) is int and _MIN_INT32 <= value <= _MAX_INT32
    if name == "ouiCombine":
        return isinstance(value, list) and len(value) <= _MAX_NESTED_ENTRIES
    return False


def _count_field(coverage: dict[str, int], name: str, value: object) -> bool:
    if value is _MISSING:
        coverage["missing"] += 1
        return False
    coverage["present"] += 1
    if _valid(name, value):
        coverage["type_valid"] += 1
        return True
    coverage["invalid"] += 1
    return False


def project_site_oui_profile_list_page(raw: object, *, page_size: int) -> dict[str, Any]:
    """Return aggregate schema coverage without profile or OUI values."""
    if (type(page_size) is not int or not 1 <= page_size <= MAX_PROFILE_ROWS or
            not isinstance(raw, Mapping) or len(raw) > 8):
        raise SiteOuiProfileListError("response_invalid")
    total = raw.get("totalRows")
    current_page = raw.get("currentPage")
    current_size = raw.get("currentSize")
    rows = raw.get("data")
    if (not _valid("totalRows", total) or type(current_page) is not int or
            current_page != 1 or not isinstance(rows, list) or len(rows) > page_size or
            len(rows) > total or (not rows and total != 0) or type(current_size) is not int or
            current_size not in (len(rows), page_size)):
        raise SiteOuiProfileListError("response_invalid")

    profile_coverage = {field: _coverage() for field in _PROFILE_FIELDS}
    oui_coverage = {field: _coverage() for field in _OUI_FIELDS}
    grid_coverage = {field: _coverage() for field in _GRID_FIELDS}
    invalid_profile_count = invalid_oui_entry_count = unknown_field_count = 0
    oui_entry_count = 0
    unknown_field_count += sum(key not in _GRID_FIELDS for key in raw)
    for field in _GRID_FIELDS:
        _count_field(grid_coverage[field], field, raw.get(field, _MISSING))
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > _MAX_FIELDS:
            invalid_profile_count += 1
            continue
        unknown_field_count += sum(key not in _PROFILE_FIELDS for key in row)
        for field in _PROFILE_FIELDS:
            value = row.get(field, _MISSING)
            _count_field(profile_coverage[field], field, value)
        entries = row.get("ouiCombine")
        if not isinstance(entries, list):
            continue
        if len(entries) > _MAX_NESTED_ENTRIES:
            invalid_oui_entry_count += len(entries)
            continue
        oui_entry_count += len(entries)
        for entry in entries:
            if not isinstance(entry, Mapping) or len(entry) > 4:
                invalid_oui_entry_count += 1
                continue
            unknown_field_count += sum(key not in _OUI_FIELDS for key in entry)
            for field in _OUI_FIELDS:
                _count_field(oui_coverage[field], field, entry.get(field, _MISSING))

    invalid_field_count = sum(item["invalid"] for item in profile_coverage.values())
    invalid_field_count += sum(item["invalid"] for item in oui_coverage.values())
    omitted = total - len(rows)
    missing_field_count = sum(item["missing"] for item in profile_coverage.values())
    missing_field_count += sum(item["missing"] for item in oui_coverage.values())
    missing_field_count += sum(item["missing"] for item in grid_coverage.values())
    invalid_field_count += sum(item["invalid"] for item in grid_coverage.values())
    return {
        "profile_count": len(rows),
        "reported_total_profiles": total,
        "omitted_profile_count": omitted,
        "grid_field_coverage": grid_coverage,
        "profile_field_coverage": profile_coverage,
        "oui_entry_count": oui_entry_count,
        "oui_field_coverage": oui_coverage,
        "invalid_profile_count": invalid_profile_count,
        "invalid_oui_entry_count": invalid_oui_entry_count,
        "invalid_field_count": invalid_field_count,
        "unknown_field_count": unknown_field_count,
        "missing_field_count": missing_field_count,
        "partial": bool(omitted or invalid_profile_count or invalid_oui_entry_count or
                         invalid_field_count or missing_field_count or unknown_field_count),
        "profile_names_ids_oui_values_descriptions_and_assignments_returned": False,
    }
