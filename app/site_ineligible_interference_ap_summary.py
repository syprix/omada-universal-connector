"""Count APs that the controller reports as ineligible for interference scans."""
from __future__ import annotations

from collections.abc import Mapping
import re


class SiteIneligibleInterferenceApError(ValueError):
    """The documented interference-detection support response is malformed."""


_MAC = re.compile(r"(?:(?:[0-9A-Fa-f]{2}:){5}|(?:[0-9A-Fa-f]{2}-){5})[0-9A-Fa-f]{2}")
MAX_APS = 500


def summarize_site_ineligible_interference_aps(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 8:
        raise SiteIneligibleInterferenceApError("result must be a bounded object")
    unknown = sum(key != "macList" for key in value)
    invalid = 0
    rows = value.get("macList")
    if rows is None and "macList" not in value:
        return {"data": {"reported_ap_count": None, "valid_ap_count": 0,
                         "truncated": False},
                "missing_field_count": 1, "invalid_field_count": 0,
                "unknown_field_count": unknown, "partial": True}
    if not isinstance(rows, list):
        raise SiteIneligibleInterferenceApError("macList must be a list")
    truncated = len(rows) > MAX_APS
    valid = 0
    for mac in rows[:MAX_APS]:
        if not isinstance(mac, str) or not _MAC.fullmatch(mac):
            invalid += 1
        else:
            valid += 1
    return {
        "data": {"reported_ap_count": len(rows), "valid_ap_count": valid,
                 "truncated": truncated},
        "missing_field_count": 0,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(invalid or unknown or truncated),
    }
