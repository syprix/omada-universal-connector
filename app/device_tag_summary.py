"""Bounded, identifier-free projection for site device tags."""
from __future__ import annotations

from typing import Any


MAX_TAGS = 256
_FIELDS = {"name", "tagId"}


class DeviceTagSummaryError(ValueError):
    """Raised when a tag response cannot be projected safely."""


def summarize_device_tags(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_TAGS:
        raise DeviceTagSummaryError("response_invalid")
    missing = invalid = unknown = id_present = name_present = 0
    for row in result:
        if not isinstance(row, dict):
            invalid += 1
            continue
        unknown += len(set(row) - _FIELDS)
        for field in ("tagId", "name"):
            value = row.get(field)
            if value is None:
                missing += 1
            elif isinstance(value, str):
                if value:
                    if field == "tagId":
                        id_present += 1
                    else:
                        name_present += 1
            else:
                invalid += 1
    return {
        "data": {
            "tag_count": len(result),
            "tag_id_present_count": id_present,
            "tag_name_present_count": name_present,
            "missing_count": missing,
            "invalid_count": invalid,
            "unknown_field_count": unknown,
        },
        "partial": bool(missing or invalid or unknown),
    }
