"""Bounded, identity-free inventory for the site's lock-to-AP selection list."""
from __future__ import annotations

from collections.abc import Mapping


class SiteLockToApBriefInventoryError(ValueError):
    """The documented lock-to-AP AP list is malformed."""


_FIELDS = frozenset((
    "mac", "name", "ip", "statusCategory", "status", "model",
    "modelVersion", "type", "showModel", "specialModel", "active",
    "supportLockToAp",
))
_STRING_FIELDS = frozenset((
    "mac", "name", "ip", "model", "modelVersion", "type", "showModel",
    "specialModel",
))
_STATUS_CATEGORIES = (0, 1, 2, 3, 4)
_STATUS_CODES = (
    0, 1, 10, 11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 25, 26, 27,
    30, 31, 32, 33, 40, 41, 50,
)
MAX_ROWS = 500


def summarize_site_lock_to_ap_brief_inventory(value: object) -> dict[str, object]:
    if not isinstance(value, list):
        raise SiteLockToApBriefInventoryError("AP inventory must be a list")
    reported = len(value)
    rows = value[:MAX_ROWS]
    category_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    support_true = support_false = support_unreported = 0
    active_true = active_false = active_unreported = 0
    invalid = unknown = valid = unknown_status_category = unknown_status = 0

    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 24:
            invalid += 1
            support_unreported += 1
            active_unreported += 1
            continue
        valid += 1
        unknown += sum(key not in _FIELDS for key in row)
        for key in _STRING_FIELDS:
            if key in row and not isinstance(row[key], str):
                invalid += 1
        for key, counts, known, unknown_attr in (
                ("statusCategory", category_counts, _STATUS_CATEGORIES,
                 "category"),
                ("status", status_counts, _STATUS_CODES, "status")):
            if key not in row:
                continue
            code = row[key]
            if type(code) is not int or not -(2**31) <= code < 2**31:
                invalid += 1
            elif code in known:
                counts[str(code)] = counts.get(str(code), 0) + 1
            elif unknown_attr == "category":
                unknown_status_category += 1
            else:
                unknown_status += 1
        if "supportLockToAp" not in row:
            support_unreported += 1
        elif type(row["supportLockToAp"]) is not bool:
            invalid += 1
            support_unreported += 1
        elif row["supportLockToAp"]:
            support_true += 1
        else:
            support_false += 1
        if "active" not in row:
            active_unreported += 1
        elif type(row["active"]) is not bool:
            invalid += 1
            active_unreported += 1
        elif row["active"]:
            active_true += 1
        else:
            active_false += 1

    truncated = reported > MAX_ROWS
    return {
        "data": {
            "reported_ap_count": reported,
            "valid_ap_record_count": valid,
            "status_category_counts": category_counts,
            "status_counts": status_counts,
            "unknown_status_category_count": unknown_status_category,
            "unknown_status_count": unknown_status,
            "lock_to_ap_support_counts": {
                "supported_count": support_true,
                "unsupported_count": support_false,
                "unreported_count": support_unreported,
            },
            "active_counts": {
                "active_count": active_true,
                "inactive_count": active_false,
                "unreported_count": active_unreported,
            },
            "truncated": truncated,
        },
        "missing_field_count": 0,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(invalid or unknown or unknown_status or
                         unknown_status_category or truncated),
    }
