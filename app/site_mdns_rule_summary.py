"""Redacted counts for configured site mDNS rules."""

from __future__ import annotations

from collections.abc import Mapping


class SiteMdnsRuleError(ValueError):
    """The controller returned an invalid mDNS rule listing."""


_PAGE_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_ROW_FIELDS = frozenset(("id", "name", "status", "profileIds", "type", "ap", "osg"))


def project_site_mdns_rules(pages: object) -> dict[str, object]:
    """Validate up to five fixed pages and aggregate rule status/type codes."""
    if not isinstance(pages, list) or not 1 <= len(pages) <= 5:
        raise SiteMdnsRuleError("pages must contain one to five bounded pages")

    missing = invalid = unknown = returned = valid = enabled = disabled = 0
    status_complete = type_complete = True
    type_counts: dict[str, int] = {}
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
            if not isinstance(row, Mapping) or len(row) > 16:
                invalid += 1
                status_complete = type_complete = False
                continue
            valid += 1
            unknown += sum(key not in _ROW_FIELDS for key in row)
            if "status" not in row:
                missing += 1
                status_complete = False
            elif not isinstance(row["status"], bool):
                invalid += 1
                status_complete = False
            elif row["status"]:
                enabled += 1
            else:
                disabled += 1
            rule_type = row.get("type")
            if "type" not in row:
                missing += 1
                type_complete = False
            elif type(rule_type) is not int:
                invalid += 1
                type_complete = False
            else:
                key = str(rule_type)
                type_counts[key] = type_counts.get(key, 0) + 1
            for key in ("id", "name"):
                if key in row and not isinstance(row[key], str):
                    invalid += 1
            if "profileIds" in row and (not isinstance(row["profileIds"], list) or
                                         len(row["profileIds"]) > 256 or
                                         any(not isinstance(x, str) for x in row["profileIds"])):
                invalid += 1
            for key, allowed in (("ap", frozenset(("serviceVlan", "clientVlan"))),
                                 ("osg", frozenset(("serviceNetworks", "clientNetworks")))):
                nested = row.get(key)
                if nested is None:
                    continue
                if not isinstance(nested, Mapping) or len(nested) > 8:
                    invalid += 1
                    continue
                unknown += sum(field not in allowed for field in nested)
                for field, value in nested.items():
                    if field in ("serviceNetworks", "clientNetworks"):
                        if not isinstance(value, list) or len(value) > 256 or any(
                                not isinstance(item, str) for item in value):
                            invalid += 1
                    elif not isinstance(value, str):
                        invalid += 1

    total = totals[0] if totals and len(set(totals)) == 1 and len(totals) == len(pages) else None
    if len(set(totals)) > 1 or (total is not None and returned > total):
        invalid += 1
    truncated = (total > returned if total is not None else
                 len(pages) == 5 and all(isinstance(p, Mapping) and
                                         isinstance(p.get("data"), list) and
                                         len(p["data"]) == 100 for p in pages))
    return {
        "data": {
            "reported_total_rule_count": total,
            "returned_rule_count": returned,
            "valid_rule_record_count": valid,
            "enabled_rule_count": enabled if status_complete else None,
            "disabled_rule_count": disabled if status_complete else None,
            "rule_type_code_counts": type_counts if type_complete else None,
            "pages_read": len(pages),
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or truncated),
    }
