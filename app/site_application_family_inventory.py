"""Bounded, redacted site application-family selectors."""
from __future__ import annotations

from collections import Counter
from typing import Any

MAX_FAMILY_ROWS = 100
INT32_MAX = (1 << 31) - 1


class SiteApplicationFamilyInventoryError(ValueError):
    """Raised when the documented family list exceeds its safe bounds."""


def project_site_application_family_inventory(result: Any) -> dict[str, object]:
    if not isinstance(result, list) or len(result) > MAX_FAMILY_ROWS:
        raise SiteApplicationFamilyInventoryError("family_rows_invalid")
    identifiers: list[int] = []
    invalid_row_count = 0
    unknown_field_count = 0
    for row in result:
        if not isinstance(row, dict) or len(row) > 8:
            invalid_row_count += 1
            continue
        unknown_field_count += len(set(row) - {"familyId", "familyName", "description"})
        family_id = row.get("familyId")
        if type(family_id) is not int or not 0 <= family_id <= INT32_MAX:
            invalid_row_count += 1
            continue
        identifiers.append(family_id)
    frequencies = Counter(identifiers)
    duplicate_family_id_count = sum(count > 1 for count in frequencies.values())
    family_refs = [str(value) for value in dict.fromkeys(identifiers)
                   if frequencies[value] == 1]
    data = {
        "family_refs": family_refs,
        "family_ref_count": len(family_refs),
        "family_row_count": len(result),
        "invalid_row_count": invalid_row_count,
        "duplicate_family_id_count": duplicate_family_id_count,
        "unknown_field_count": unknown_field_count,
    }
    return {"data": data,
            "partial": bool(invalid_row_count or duplicate_family_id_count or
                            unknown_field_count)}
