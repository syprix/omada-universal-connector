"""Redacted coverage for the controller-wide placed-site position list."""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

MAX_PLACED_SITE_ROWS = 10_000
MAX_ROW_FIELDS = 64
MAX_STRING_LENGTH = 4096
_FIELDS = frozenset({"id", "region", "name", "longitude", "latitude", "address"})
_STRINGS = frozenset({"id", "region", "name", "address"})
_COORDINATES = frozenset({"longitude", "latitude"})


class ControllerPlacedSitePositionError(ValueError):
    """Invalid or overlarge placed-site response."""


def _coordinate_shape(value: Any) -> str:
    # Hardware/CBC describe coordinates as numbers. ER7212PC describes them as
    # opaque objects; no object member is interpreted as a coordinate value.
    if type(value) is int or type(value) is float:
        try:
            return "number" if math.isfinite(float(value)) else "invalid"
        except (OverflowError, ValueError):
            return "invalid"
    if isinstance(value, Mapping):
        return "object"
    return "invalid"


def summarize_placed_site_positions(result: Any, *, result_present: bool = True) -> dict[str, object]:
    """Return list/field shape counts only; never return site data or claim completeness."""
    if type(result_present) is not bool:
        raise ControllerPlacedSitePositionError("presence_flag_invalid")

    state: str
    rows: list[Any] | None
    if not result_present:
        state, rows = "missing", None
    elif not isinstance(result, list):
        state, rows = "invalid", None
    elif len(result) > MAX_PLACED_SITE_ROWS:
        return {
            "source_state": "too_large",
            "placed_site_row_count": len(result),
            "invalid_row_count": 0,
            "documented_field_count": len(_FIELDS),
            "documented_field_observed_count": 0,
            "documented_field_presence_count": 0,
            "documented_field_missing_count": 0,
            "documented_field_type_valid_count": 0,
            "documented_field_type_invalid_count": 0,
            "rows_with_all_documented_fields_count": 0,
            "unknown_field_count": 0,
            "coordinate_number_value_count": 0,
            "coordinate_object_shape_count": 0,
            "coordinate_invalid_shape_count": 0,
            "empty": False,
            "partial": True,
            "server_completeness_established": False,
        }
    else:
        rows = result
        state = "empty" if not rows else "present"

    if rows is None:
        return {
            "source_state": state,
            "placed_site_row_count": None,
            "invalid_row_count": 0,
            "documented_field_count": len(_FIELDS),
            "documented_field_observed_count": 0,
            "documented_field_presence_count": 0,
            "documented_field_missing_count": 0,
            "documented_field_type_valid_count": 0,
            "documented_field_type_invalid_count": 0,
            "rows_with_all_documented_fields_count": 0,
            "unknown_field_count": 0,
            "coordinate_number_value_count": 0,
            "coordinate_object_shape_count": 0,
            "coordinate_invalid_shape_count": 0,
            "empty": False,
            "partial": True,
            "server_completeness_established": False,
        }

    invalid_rows = unknown_fields = field_presence = field_missing = 0
    valid_fields = invalid_fields = complete_rows = 0
    observed: set[str] = set()
    coordinate_numbers = coordinate_objects = coordinate_invalid = 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > MAX_ROW_FIELDS:
            invalid_rows += 1
            continue
        unknown_fields += sum(key not in _FIELDS for key in row)
        missing = 0
        invalid = 0
        for field in _FIELDS:
            if field not in row:
                field_missing += 1
                missing += 1
                continue
            field_presence += 1
            observed.add(field)
            value = row[field]
            if field in _STRINGS:
                valid = isinstance(value, str) and len(value) <= MAX_STRING_LENGTH
            elif field in _COORDINATES:
                shape = _coordinate_shape(value)
                coordinate_numbers += shape == "number"
                coordinate_objects += shape == "object"
                coordinate_invalid += shape == "invalid"
                valid = shape in {"number", "object"}
            else:  # Defensive against accidental schema drift.
                valid = False
            if valid:
                valid_fields += 1
            else:
                invalid_fields += 1
                invalid += 1
        if not missing and not invalid:
            complete_rows += 1

    partial = bool(state not in {"empty", "present"} or invalid_rows or unknown_fields or
                    field_missing or invalid_fields)
    return {
        "source_state": state,
        "placed_site_row_count": len(rows),
        "invalid_row_count": invalid_rows,
        "documented_field_count": len(_FIELDS),
        "documented_field_observed_count": len(observed),
        "documented_field_presence_count": field_presence,
        "documented_field_missing_count": field_missing,
        "documented_field_type_valid_count": valid_fields,
        "documented_field_type_invalid_count": invalid_fields,
        "rows_with_all_documented_fields_count": complete_rows,
        "unknown_field_count": unknown_fields,
        "coordinate_number_value_count": coordinate_numbers,
        "coordinate_object_shape_count": coordinate_objects,
        "coordinate_invalid_shape_count": coordinate_invalid,
        "empty": state == "empty",
        "partial": partial,
        "server_completeness_established": False,
    }
