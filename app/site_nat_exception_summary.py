"""Redacted summary of site NAT exception configuration rows."""
from __future__ import annotations

from collections.abc import Mapping


class SiteNatExceptionSummaryError(ValueError):
    pass


_PAGE_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_ROW_FIELDS = frozenset(("id", "name", "status", "lanList", "description", "interface"))


def summarize_site_nat_exceptions(pages: object, *, max_items: int = 1000) -> dict[str, object]:
    if (not isinstance(pages, list) or not 1 <= len(pages) <= 100 or
            type(max_items) is not int or not 1 <= max_items <= 10_000):
        raise SiteNatExceptionSummaryError("invalid page set")

    total_values: list[int] = []
    selected_rows: list[object] = []
    missing_field_count = invalid_field_count = unknown_field_count = 0
    for page_number, page in enumerate(pages, 1):
        if not isinstance(page, Mapping) or len(page) > 16:
            invalid_field_count += 1
            continue
        unknown_field_count += sum(field not in _PAGE_FIELDS for field in page)
        total = page.get("totalRows")
        current = page.get("currentPage")
        size = page.get("currentSize")
        rows = page.get("data")
        if type(total) is int and total >= 0:
            total_values.append(total)
        else:
            missing_field_count += 1 if "totalRows" not in page else 0
            invalid_field_count += 1 if "totalRows" in page else 0
        if type(current) is not int or current != page_number:
            missing_field_count += 1 if "currentPage" not in page else 0
            invalid_field_count += 1 if "currentPage" in page else 0
        if not isinstance(rows, list) or len(rows) > 1000:
            missing_field_count += 1 if "data" not in page else 0
            invalid_field_count += 1 if "data" in page else 0
            continue
        if type(size) is not int or size not in (len(rows), 100):
            missing_field_count += 1 if "currentSize" not in page else 0
            invalid_field_count += 1 if "currentSize" in page else 0
        selected_rows.extend(rows)

    if len(set(total_values)) > 1:
        invalid_field_count += 1
    total = (total_values[0] if len(total_values) == len(pages) and
             total_values and len(set(total_values)) == 1 else None)
    if total is not None and len(selected_rows) > total:
        invalid_field_count += 1
    rows = selected_rows[:max_items]

    status_counts = {"enabled": 0, "disabled": 0, "unreported": 0}
    lan_coverage = {"with_entries": 0, "empty": 0, "unreported": 0}
    interface_coverage = {"configured": 0, "empty": 0, "unreported": 0}
    lan_entry_count = 0
    invalid_record_count = 0

    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 32:
            invalid_record_count += 1
            status_counts["unreported"] += 1
            lan_coverage["unreported"] += 1
            interface_coverage["unreported"] += 1
            continue
        unknown_field_count += sum(field not in _ROW_FIELDS for field in row)
        missing_field_count += sum(field not in row for field in ("name", "status", "lanList", "interface"))
        status = row.get("status")
        if type(status) is bool:
            status_counts["enabled" if status else "disabled"] += 1
        else:
            status_counts["unreported"] += 1
            invalid_field_count += 1 if status is not None else 0

        lan_list = row.get("lanList")
        if isinstance(lan_list, list) and len(lan_list) <= 512 and all(
                isinstance(value, str) and len(value) <= 128 for value in lan_list):
            lan_entry_count += len(lan_list)
            lan_coverage["with_entries" if lan_list else "empty"] += 1
        else:
            lan_coverage["unreported"] += 1
            invalid_field_count += 1 if lan_list is not None else 0

        interface = row.get("interface")
        if isinstance(interface, str) and len(interface) <= 128:
            interface_coverage["configured" if interface.strip() else "empty"] += 1
        else:
            interface_coverage["unreported"] += 1
            invalid_field_count += 1 if interface is not None else 0

        if "name" in row and (not isinstance(row["name"], str) or len(row["name"]) > 128):
            invalid_field_count += 1

    truncated = (total is not None and len(selected_rows) < total) or len(selected_rows) > max_items
    return {
        "resource": "site_nat_exception_summary",
        "scope": "configured_nat_exception_rules",
        "reported_rule_count": total,
        "returned_rule_count": len(rows),
        "rule_status_counts": status_counts,
        "lan_list_coverage_counts": lan_coverage,
        "lan_entry_count": lan_entry_count,
        "wan_interface_coverage_counts": interface_coverage,
        "pages_read": len(pages),
        "missing_field_count": missing_field_count,
        "invalid_record_count": invalid_record_count,
        "invalid_field_count": invalid_field_count,
        "unknown_field_count": unknown_field_count,
        "truncated": truncated,
        "partial": bool(missing_field_count or invalid_record_count or invalid_field_count
                         or unknown_field_count or truncated or total is None),
    }
