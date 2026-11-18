"""Redacted counts for a site's DHCP reservation list."""

from __future__ import annotations

from collections.abc import Mapping


class SiteDhcpReservationError(ValueError):
    """The controller returned an invalid DHCP reservation response."""


_PAGE_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data",
                          "supportOptions", "netNameToIdMap"))
_ROW_FIELDS = frozenset((
    "id", "description", "netId", "netName", "mac", "ip", "options", "status",
    "exportToIpMacBinding", "clientName", "name", "existOptions", "type",
    "showingType", "model", "modelVersion", "serverName", "serverType", "serverMac",
    "serverStackId", "abnormal", "featureDescription",
))
_STRING_FIELDS = frozenset((
    "id", "description", "netId", "netName", "mac", "ip", "clientName", "name",
    "showingType", "model", "modelVersion", "serverName", "serverType", "serverMac",
    "serverStackId",
))
_BOOL_FIELDS = frozenset(("status", "exportToIpMacBinding"))
_LIST_FIELDS = frozenset(("options", "existOptions", "featureDescription"))


def project_site_dhcp_reservations(pages: object) -> dict[str, object]:
    """Validate up to five fixed pages and return aggregate counts only."""
    if not isinstance(pages, list) or not 1 <= len(pages) <= 5:
        raise SiteDhcpReservationError("pages must contain one to five bounded pages")

    missing = invalid = unknown = returned = valid = 0
    enabled = disabled = device = client = other_type = 0
    status_complete = type_complete = True
    totals: list[int] = []
    truncated = False

    for expected_page, page in enumerate(pages, 1):
        if not isinstance(page, Mapping) or len(page) > 16:
            invalid += 1
            continue
        unknown += sum(key not in _PAGE_FIELDS for key in page)
        for key in ("totalRows", "currentPage", "currentSize"):
            value = page.get(key)
            if key not in page:
                missing += 1
            elif type(value) is not int or value < 0:
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
                status_complete = type_complete = False
                continue
            valid += 1
            unknown += sum(key not in _ROW_FIELDS for key in row)
            for key in _STRING_FIELDS:
                if key in row and not isinstance(row[key], str):
                    invalid += 1
            for key in _BOOL_FIELDS:
                if key not in row:
                    if key == "status":
                        missing += 1
                        status_complete = False
                elif not isinstance(row[key], bool):
                    invalid += 1
                    if key == "status":
                        status_complete = False
                elif key == "status":
                    if row[key]:
                        enabled += 1
                    else:
                        disabled += 1
            for key in _LIST_FIELDS:
                if key in row:
                    if not isinstance(row[key], list) or len(row[key]) > 256:
                        invalid += 1
                    elif key == "existOptions" and any(type(value) is not int
                                                        for value in row[key]):
                        invalid += 1
                    elif key == "options" and any(not isinstance(value, Mapping)
                                                   for value in row[key]):
                        invalid += 1
                    elif key == "featureDescription" and any(not isinstance(value, Mapping)
                                                              for value in row[key]):
                        invalid += 1
            if "abnormal" in row and type(row["abnormal"]) is not int:
                invalid += 1
            kind = row.get("type")
            if "type" not in row:
                missing += 1
                type_complete = False
            elif type(kind) is not int:
                invalid += 1
                type_complete = False
            elif kind == 0:
                device += 1
            elif kind == 1:
                client += 1
            else:
                other_type += 1

    reported_total = totals[0] if totals and len(set(totals)) == 1 else None
    if len(set(totals)) > 1:
        invalid += 1
    if len(totals) != len(pages):
        reported_total = None
    if reported_total is not None:
        if returned > reported_total:
            invalid += 1
        truncated = reported_total > returned and (len(pages) == 5 or returned < reported_total)
    elif len(pages) == 5 and all(isinstance(p, Mapping) and
                                 isinstance(p.get("data"), list) and len(p["data"]) == 100
                                 for p in pages):
        truncated = True

    return {
        "data": {
            "reported_total_reservation_count": reported_total,
            "returned_reservation_count": returned,
            "valid_reservation_record_count": valid,
            "enabled_reservation_count": enabled if status_complete else None,
            "disabled_reservation_count": disabled if status_complete else None,
            "device_reservation_count": device if type_complete else None,
            "client_reservation_count": client if type_complete else None,
            "other_type_reservation_count": other_type if type_complete else None,
            "pages_read": len(pages),
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or truncated),
    }
