"""Count automatic ONU discoveries without returning authentication material."""
from __future__ import annotations

from typing import Any

MAX_ROWS = 100
MAX_FIELDS = 32
MAX_PAGE = 10_000
MAX_PAGE_SIZE = 100


class OltAutofindInventoryError(ValueError):
    """Raised for malformed discovery pages."""


def project_olt_autofind_inventory_page(result: Any, *, page_number: int,
                                        page_size: int) -> dict[str, object]:
    if (type(page_number) is not int or not 0 <= page_number <= MAX_PAGE or
            type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE or
            not isinstance(result, list) or len(result) > page_size or len(result) > MAX_ROWS):
        raise OltAutofindInventoryError("response_invalid")
    invalid = unknown = redacted = 0
    allowed = {"key", "portId", "serialNumber", "macAddress", "passwordType", "password",
               "loid", "loidPassword", "hardwareVersion", "softwareVersion", "vendorId",
               "equipmentId"}
    for row in result:
        if not isinstance(row, dict) or len(row) > MAX_FIELDS:
            invalid += 1
            continue
        unknown += len(set(row) - allowed)
        redacted += len(row)
        key = row.get("key")
        if key is not None and (not isinstance(key, str) or len(key) > 256):
            invalid += 1
    return {
        "data": {"discovered_onu_count": len(result),
                 "page_number": page_number, "page_size": page_size,
                 "page_may_be_truncated": len(result) == page_size},
        "partial": bool(invalid or unknown or len(result) == page_size),
        "missing_count": 0, "invalid_count": invalid,
        "unknown_field_count": unknown, "redacted_field_count": redacted,
    }
