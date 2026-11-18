"""Redacted summaries for fixed switch QoS scheduler and DSCP mapping reads."""
from __future__ import annotations

from typing import Any


class SwitchQosMappingError(ValueError):
    """Raised for an invalid or unbounded switch QoS mapping response."""


def _int32(value: Any) -> bool:
    return type(value) is int and -(2 ** 31) <= value < 2 ** 31


def project_scheduler_mapping(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 12:
        raise SwitchQosMappingError("response_invalid")
    known = {"id", "name", "types", "mapping", "buildIn"}
    missing = invalid = unknown = rows_invalid = valid_rows = 0
    data: dict[str, object] = {}
    for field, target in (("id", "id_present"), ("name", "name_present")):
        if field not in result:
            continue
        value = result[field]
        if isinstance(value, str) and len(value) <= 128:
            data[target] = bool(value)
        else:
            invalid += 1
    if "types" in result:
        if _int32(result["types"]):
            data["type_configured"] = True
        else:
            invalid += 1
    if "buildIn" in result:
        if type(result["buildIn"]) is bool:
            data["built_in"] = result["buildIn"]
        else:
            invalid += 1
    if "mapping" not in result:
        missing += 1
    else:
        rows = result["mapping"]
        if not isinstance(rows, list) or len(rows) > 64:
            invalid += 1
        else:
            present = {"queue": 0, "type": 0, "weight": 0}
            for row in rows:
                if not isinstance(row, dict) or len(row) > 8:
                    rows_invalid += 1
                    continue
                row_valid = True
                for field in present:
                    if field not in row:
                        if field in {"queue", "type"}:
                            rows_invalid += 1
                            row_valid = False
                    elif _int32(row[field]):
                        present[field] += 1
                    else:
                        rows_invalid += 1
                        row_valid = False
                valid_rows += int(row_valid)
            data.update({"mapping_count": len(rows), "rows_with_valid_fields": valid_rows,
                         "queue_value_count": present["queue"],
                         "scheduler_type_value_count": present["type"],
                         "weight_value_count": present["weight"]})
            invalid += rows_invalid
    unknown += len(set(result) - known)
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}


def project_dscp_mapping(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SwitchQosMappingError("response_invalid")
    if "mapping" not in result:
        return {"data": {"queue_count": 0, "mapped_value_count": 0},
                "missing_field_count": 1, "invalid_field_count": 0,
                "unknown_field_count": len(set(result)), "partial": True}
    mapping = result["mapping"]
    if not isinstance(mapping, dict) or len(mapping) > 32:
        raise SwitchQosMappingError("response_invalid")
    invalid = unknown = value_count = 0
    for queue, values in mapping.items():
        if not isinstance(queue, str) or not queue or len(queue) > 32:
            invalid += 1
        if not isinstance(values, list) or len(values) != 8:
            invalid += 1
            continue
        if any(not _int32(value) for value in values):
            invalid += 1
        else:
            value_count += len(values)
    unknown = len(set(result) - {"mapping"})
    return {"data": {"queue_count": len(mapping),
                     "mapped_value_count": value_count},
            "missing_field_count": 0, "invalid_field_count": invalid,
            "unknown_field_count": unknown,
            "partial": bool(invalid or unknown)}
