"""Bounded coverage projection for the documented site portal list."""
from __future__ import annotations

from typing import Any


MAX_PORTALS = 256
MAX_PORTAL_FIELDS = 64
MAX_BOUND_ROWS_PER_PORTAL = 256


class SitePortalInventoryError(ValueError):
    """Raised when the fixed portal-list response is malformed or over bound."""


def _activation_coverage(rows: list[Any], unreadable: int) -> dict[str, int]:
    true_count = false_count = missing = invalid = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if "enable" not in row:
            missing += 1
        elif type(row["enable"]) is bool:
            if row["enable"]:
                true_count += 1
            else:
                false_count += 1
        else:
            invalid += 1
    return {"true_count": true_count, "false_count": false_count,
            "missing_count": missing, "invalid_count": invalid,
            "uninspected_portal_count": unreadable}


def _list_coverage(rows: list[Any], field: str, unreadable: int) -> dict[str, int]:
    present = missing = invalid = empty = entry_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if field not in row:
            missing += 1
            continue
        value = row[field]
        if not isinstance(value, list):
            invalid += 1
            continue
        if len(value) > MAX_BOUND_ROWS_PER_PORTAL:
            raise SitePortalInventoryError("response_invalid")
        if any(not isinstance(item, str) for item in value):
            invalid += 1
            continue
        present += 1
        empty += int(not value)
        entry_count += len(value)
    return {"present_count": present, "missing_count": missing,
            "invalid_count": invalid, "empty_count": empty,
            "entry_count": entry_count,
            "uninspected_portal_count": unreadable}


def summarize_site_portal_inventory(result: Any) -> dict[str, object]:
    """Return only row counts and coverage; discard all portal properties."""
    if not isinstance(result, list) or len(result) > MAX_PORTALS:
        raise SitePortalInventoryError("response_invalid")

    unreadable = 0
    for row in result:
        if not isinstance(row, dict):
            unreadable += 1
        elif len(row) > MAX_PORTAL_FIELDS:
            raise SitePortalInventoryError("response_invalid")

    activation = _activation_coverage(result, unreadable)
    ssids = _list_coverage(result, "ssidList", unreadable)
    networks = _list_coverage(result, "networkList", unreadable)
    partial = bool(
        unreadable or activation["missing_count"] or activation["invalid_count"] or
        ssids["missing_count"] or ssids["invalid_count"] or
        networks["missing_count"] or networks["invalid_count"])
    return {
        "data": {
            "portal_count": len(result),
            "empty": not result,
            "activation_coverage": activation,
            "ssid_list_coverage": ssids,
            "network_list_coverage": networks,
            "unreadable_portal_count": unreadable,
            "truncation_status": "not_reported_by_contract",
        },
        "partial": partial,
    }
