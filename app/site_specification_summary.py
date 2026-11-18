"""Validated projection for documented site specification capacities."""
from __future__ import annotations

from typing import Any


class SiteSpecificationSummaryError(ValueError):
    """Raised when a specification response has an unsafe shape."""


_FIELDS = {
    "interfaceNum": "supported_interface_count",
    "urlFilteringNum": "supported_url_filtering_count",
    "macGroupAddressNum": "supported_mac_group_address_count",
}


def project_site_specification_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 12:
        raise SiteSpecificationSummaryError("site_specification_invalid")
    data: dict[str, int | None] = {}
    missing = invalid = 0
    for source, target in _FIELDS.items():
        value = result.get(source)
        if source not in result:
            missing += 1
            data[target] = None
        elif type(value) is int and 0 <= value <= 2**31 - 1:
            data[target] = value
        else:
            invalid += 1
            data[target] = None
    unknown = len(set(result) - set(_FIELDS))
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
