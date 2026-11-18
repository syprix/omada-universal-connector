"""Bounded WLAN-group SSID diagnostics with identifiers and VLAN data removed."""

from __future__ import annotations

from collections.abc import Mapping


class SiteWlanGroupSsidsSummaryError(ValueError):
    """The paginated WLAN-group SSID result is malformed."""


_PAGE_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_SSID_FIELDS = frozenset((
    "ssidId", "id", "name", "description", "chooseDevices", "band",
    "guestNetEnable", "security", "broadcast", "vlanEnable", "vlanId",
    "vlanPoolIds",
))
_FLAG_FIELDS = {
    "description": "ssid_enabled",
    "guestNetEnable": "guest_network_enabled",
    "broadcast": "broadcast_enabled",
    "vlanEnable": "vlan_enabled",
}
_SECURITY_CODES = (0, 2, 3, 4, 5)


def project_site_wlan_group_ssids(pages: object) -> dict[str, object]:
    """Summarize up to 500 SSIDs, counting variant-only fields as unreported."""
    if not isinstance(pages, list) or not 1 <= len(pages) <= 5:
        raise SiteWlanGroupSsidsSummaryError("pages must contain one to five pages")

    missing = invalid = unknown = returned = valid = 0
    totals: list[int] = []
    truncated = False
    flags = {name: {"enabled_count": 0, "disabled_count": 0,
                    "unreported_count": 0} for name in _FLAG_FIELDS.values()}
    band_counts = {"2.4GHz": 0, "5GHz": 0, "6GHz": 0}
    unreported_band = unknown_band = 0
    security_counts = {str(code): 0 for code in _SECURITY_CODES}
    unreported_security = unknown_security = 0

    for page_number, page in enumerate(pages, 1):
        if not isinstance(page, Mapping) or len(page) > 16:
            invalid += 1
            continue
        unknown += sum(key not in _PAGE_FIELDS for key in page)
        for field in _PAGE_FIELDS:
            if field not in page:
                missing += 1
        total, current_page = page.get("totalRows"), page.get("currentPage")
        if type(total) is int and total >= 0:
            totals.append(total)
        elif "totalRows" in page:
            invalid += 1
        if type(current_page) is not int or current_page != page_number:
            if "currentPage" in page:
                invalid += 1
        rows = page.get("data")
        if not isinstance(rows, list) or len(rows) > 100:
            if "data" in page:
                invalid += 1
            continue
        if type(page.get("currentSize")) is not int or page["currentSize"] != len(rows):
            if "currentSize" in page:
                invalid += 1
        returned += len(rows)
        for row in rows:
            if not isinstance(row, Mapping) or len(row) > 24:
                invalid += 1
                for counts in flags.values():
                    counts["unreported_count"] += 1
                unreported_band += 1
                unreported_security += 1
                continue
            valid += 1
            unknown += sum(key not in _SSID_FIELDS for key in row)
            for source, target in _FLAG_FIELDS.items():
                counts = flags[target]
                if source not in row:
                    counts["unreported_count"] += 1
                elif type(row[source]) is not bool:
                    invalid += 1
                    counts["unreported_count"] += 1
                elif row[source]:
                    counts["enabled_count"] += 1
                else:
                    counts["disabled_count"] += 1

            band = row.get("band")
            if "band" not in row:
                unreported_band += 1
            elif type(band) is not int:
                invalid += 1
                unreported_band += 1
            elif 0 <= band <= 7:
                for bit, key in enumerate(("2.4GHz", "5GHz", "6GHz")):
                    band_counts[key] += bool(band & (1 << bit))
            else:
                unknown_band += 1

            security = row.get("security")
            if "security" not in row:
                unreported_security += 1
            elif type(security) is not int:
                invalid += 1
                unreported_security += 1
            elif str(security) in security_counts:
                security_counts[str(security)] += 1
            else:
                unknown_security += 1

    total = (totals[0] if len(totals) == len(pages) and
             len(set(totals)) == 1 else None)
    if len(set(totals)) > 1 or (total is not None and returned > total):
        invalid += 1
    truncated = total > returned if total is not None else (
        len(pages) == 5 and all(isinstance(p, Mapping) and
                                isinstance(p.get("data"), list) and
                                len(p["data"]) == 100 for p in pages))
    return {
        "data": {
            "reported_total_ssid_count": total,
            "returned_ssid_count": returned,
            "valid_ssid_record_count": valid,
            "ssid_flag_counts": flags,
            "band_coverage_counts": band_counts,
            "unreported_band_count": unreported_band,
            "unknown_band_code_count": unknown_band,
            "security_code_counts": security_counts,
            "unreported_security_count": unreported_security,
            "unknown_security_code_count": unknown_security,
            "pages_read": len(pages),
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or unknown_band or
                        unknown_security or truncated),
    }
