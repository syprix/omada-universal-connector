"""Identity-free projection for MSP device tags."""
from __future__ import annotations

from typing import Any

MAX_TAGS = 1_000


class MspDeviceTagsError(ValueError):
    """Raised when the documented tag list exceeds its shape bounds."""


def project_msp_device_tags(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_TAGS:
        raise MspDeviceTagsError("response_invalid")
    valid_count = 0
    id_present_count = 0
    invalid_count = 0
    unknown_field_count = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 4:
            raise MspDeviceTagsError("response_invalid")
        unknown_field_count += len(set(row) - {"name", "tagId"})
        name = row.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 128:
            invalid_count += 1
        else:
            valid_count += 1
        tag_id = row.get("tagId")
        if tag_id is not None:
            if isinstance(tag_id, str) and len(tag_id) <= 256:
                id_present_count += bool(tag_id)
            else:
                invalid_count += 1
    return {
        "data": {
            "tag_count": valid_count,
            "tag_id_present_count": id_present_count,
            "invalid_count": invalid_count,
            "unknown_field_count": unknown_field_count,
        },
        "partial": bool(invalid_count or unknown_field_count),
    }
