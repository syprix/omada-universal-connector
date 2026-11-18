"""Redacted, bounded counts for configured DHCP snooping devices."""

from __future__ import annotations

from collections.abc import Mapping


class SiteDhcpSnoopsError(ValueError):
    """The controller returned an invalid DHCP snooping listing."""


_PAGE_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_ROW_FIELDS = frozenset((
    "id", "omadacId", "siteId", "name", "mac", "deviceName", "deviceType",
    "deviceModel", "deviceModelVersion", "showModel", "stackId", "stackName",
    "oswStack", "ports", "status", "unSelectedablePorts", "allPorts", "allLags", "devices",
))
_STRING_FIELDS = frozenset((
    "id", "omadacId", "siteId", "name", "mac", "deviceName", "deviceType",
    "deviceModel", "deviceModelVersion", "showModel", "stackId", "stackName",
))


def project_site_dhcp_snoops(pages: object) -> dict[str, object]:
    """Validate up to five pages, returning type/status aggregates only."""
    if not isinstance(pages, list) or not 1 <= len(pages) <= 5:
        raise SiteDhcpSnoopsError("pages must contain one to five bounded pages")

    missing = invalid = unknown = returned = valid = 0
    type_complete = status_complete = True
    type_counts = {key: 0 for key in ("ap", "gateway", "switch", "olt", "other")}
    status_counts: dict[str, int] = {}
    totals: list[int] = []

    for expected_page, page in enumerate(pages, 1):
        if not isinstance(page, Mapping) or len(page) > 12:
            invalid += 1
            continue
        unknown += sum(key not in _PAGE_FIELDS for key in page)
        for key in ("totalRows", "currentPage", "currentSize"):
            if key not in page:
                missing += 1
                continue
            value = page[key]
            if type(value) is not int or value < 0:
                invalid += 1
            elif key == "totalRows":
                totals.append(value)
            elif key == "currentPage" and value != expected_page:
                invalid += 1
        rows = page.get("data")
        if "data" not in page:
            missing += 1
            continue
        if not isinstance(rows, list) or len(rows) > 100:
            invalid += 1
            continue
        current_size = page.get("currentSize")
        if type(current_size) is int and current_size != len(rows):
            invalid += 1
        returned += len(rows)
        for row in rows:
            if not isinstance(row, Mapping) or len(row) > 64:
                invalid += 1
                type_complete = status_complete = False
                continue
            valid += 1
            unknown += sum(key not in _ROW_FIELDS for key in row)
            for key in _STRING_FIELDS:
                if key in row and not isinstance(row[key], str):
                    invalid += 1
            device_type = row.get("deviceType")
            if "deviceType" not in row:
                missing += 1
                type_complete = False
            elif not isinstance(device_type, str):
                invalid += 1
                type_complete = False
            elif device_type in type_counts and device_type != "other":
                type_counts[device_type] += 1
            else:
                type_counts["other"] += 1
                if device_type != "other":
                    unknown += 1
            status = row.get("status")
            if "status" not in row:
                missing += 1
                status_complete = False
            elif type(status) is not int:
                invalid += 1
                status_complete = False
            else:
                key = str(status)
                status_counts[key] = status_counts.get(key, 0) + 1

    total = totals[0] if totals and len(set(totals)) == 1 and len(totals) == len(pages) else None
    if len(set(totals)) > 1 or (total is not None and returned > total):
        invalid += 1
    truncated = (total > returned if total is not None else
                 len(pages) == 5 and all(isinstance(p, Mapping) and
                                         isinstance(p.get("data"), list) and
                                         len(p["data"]) == 100 for p in pages))
    return {
        "data": {
            "reported_total_device_count": total,
            "returned_device_count": returned,
            "valid_device_record_count": valid,
            "device_type_counts": type_counts if type_complete else None,
            "connected_status_code_counts": status_counts if status_complete else None,
            "pages_read": len(pages),
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or truncated),
    }
