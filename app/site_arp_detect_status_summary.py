"""Validated read projection for site ARP-detection enablement flags."""
from __future__ import annotations

from typing import Any


class SiteArpDetectStatusSummaryError(ValueError):
    """Raised when the documented ARP status response has an invalid shape."""


_FIELDS = {"arpDetectEnable", "snoopForEntryEnable"}


def project_site_arp_detect_status_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteArpDetectStatusSummaryError("arp_detect_status_invalid")
    values: dict[str, bool | None] = {}
    missing = invalid = 0
    unknown = len(set(result) - _FIELDS)
    for source, public in (("arpDetectEnable", "arp_detection_enabled"),
                           ("snoopForEntryEnable", "snoop_for_entry_enabled")):
        if source not in result:
            missing += 1
            values[public] = None
        elif type(result[source]) is bool:
            values[public] = result[source]
        else:
            invalid += 1
            values[public] = None
    return {"data": values, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
