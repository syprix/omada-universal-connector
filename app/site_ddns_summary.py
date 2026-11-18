"""Redacted, bounded counts for a site's Dynamic DNS configuration."""

from __future__ import annotations

from collections.abc import Mapping


class SiteDdnsError(ValueError):
    """The controller returned an invalid Dynamic DNS listing."""


_PAGE_FIELDS = frozenset((
    "totalRows", "currentPage", "currentSize", "data", "supportCustomDdns",
    "supportCustomInterval", "supportTpLinkddns", "supportByDsLiteAndMapE",
))
_ROW_FIELDS = frozenset((
    "id", "service", "status", "interfacePortId", "username", "password", "domainName",
    "updateInterval", "customInterval", "updateUrl", "existCustomDdns",
    "existCustomInterval", "existTpLinkddns",
))
_STRING_FIELDS = frozenset(("id", "interfacePortId", "username", "password",
                            "domainName", "updateUrl"))
_BOOL_FIELDS = frozenset(("status", "existCustomDdns", "existCustomInterval",
                          "existTpLinkddns"))


def project_site_ddns(pages: object) -> dict[str, object]:
    """Validate up to five fixed pages and aggregate DDNS service/status counts."""
    if not isinstance(pages, list) or not 1 <= len(pages) <= 5:
        raise SiteDdnsError("pages must contain one to five bounded pages")
    missing = invalid = unknown = returned = valid = enabled = disabled = 0
    unknown_service_codes = 0
    status_complete = service_complete = True
    service_counts: dict[str, int] = {}
    totals: list[int] = []
    support_values: dict[str, list[object]] = {
        key: [] for key in ("supportCustomDdns", "supportCustomInterval",
                            "supportTpLinkddns", "supportByDsLiteAndMapE")}
    for expected_page, page in enumerate(pages, 1):
        if not isinstance(page, Mapping) or len(page) > 16:
            invalid += 1
            continue
        unknown += sum(key not in _PAGE_FIELDS for key in page)
        for key in ("supportCustomDdns", "supportCustomInterval", "supportByDsLiteAndMapE"):
            if key in page and not isinstance(page[key], bool):
                invalid += 1
        if "supportTpLinkddns" in page and type(page["supportTpLinkddns"]) is not int:
            invalid += 1
        for key, values in support_values.items():
            if key not in page:
                missing += 1
            elif ((key == "supportTpLinkddns" and type(page[key]) is int) or
                  (key != "supportTpLinkddns" and isinstance(page[key], bool))):
                values.append(page[key])
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
            if not isinstance(row, Mapping) or len(row) > 32:
                invalid += 1
                status_complete = service_complete = False
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
            for key in ("updateInterval", "customInterval"):
                if key in row and type(row[key]) is not int:
                    invalid += 1
            service = row.get("service")
            if "service" not in row:
                missing += 1
                service_complete = False
            elif type(service) is not int:
                invalid += 1
                service_complete = False
            else:
                key = str(service)
                service_counts[key] = service_counts.get(key, 0) + 1
                if service not in range(6):
                    unknown_service_codes += 1

    total = totals[0] if totals and len(set(totals)) == 1 and len(totals) == len(pages) else None
    if len(set(totals)) > 1 or (total is not None and returned > total):
        invalid += 1
    truncated = (total > returned if total is not None else
                 len(pages) == 5 and all(isinstance(p, Mapping) and
                                         isinstance(p.get("data"), list) and
                                         len(p["data"]) == 100 for p in pages))
    support_flags: dict[str, object] = {}
    for key, values in support_values.items():
        if len(values) == len(pages) and len(set(values)) == 1:
            support_flags[key] = values[0]
        else:
            support_flags[key] = None
            if len(values) == len(pages) and len(set(values)) > 1:
                invalid += 1
    return {
        "data": {
            "reported_total_ddns_count": total,
            "returned_ddns_count": returned,
            "valid_ddns_record_count": valid,
            "enabled_ddns_count": enabled if status_complete else None,
            "disabled_ddns_count": disabled if status_complete else None,
            "service_code_counts": service_counts if service_complete else None,
            "unknown_service_code_count": unknown_service_codes,
            "support_flags": support_flags,
            "pages_read": len(pages),
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or truncated),
    }
