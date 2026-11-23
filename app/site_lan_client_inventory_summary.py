"""Redacted summary of the paginated LAN client inventory endpoint."""
from __future__ import annotations

from collections.abc import Mapping


class LanClientInventoryError(ValueError):
    pass


_ROW_FIELDS = frozenset(("mac", "name", "type"))


def summarize_lan_client_pages(pages: object, *, page_size: int = 100,
                               max_pages: int = 10) -> dict[str, object]:
    if (not isinstance(pages, list) or not pages or len(pages) > max_pages or
            type(page_size) is not int or page_size < 1 or
            type(max_pages) is not int or max_pages < 1):
        raise LanClientInventoryError("invalid page set")
    rows: list[object] = []
    total_rows: int | None = None
    invalid = unknown = typed = missing_type = 0
    type_counts = {"reported": 0, "unreported": 0}
    for expected_page, page in enumerate(pages, 1):
        if not isinstance(page, Mapping) or len(page) > 16:
            raise LanClientInventoryError("invalid page envelope")
        data = page.get("data")
        total = page.get("totalRows")
        current = page.get("currentPage")
        size = page.get("currentSize")
        if (not isinstance(data, list) or type(total) is not int or total < 0 or
                type(current) is not int or current != expected_page or
                type(size) is not int or size not in (len(data), page_size) or
                len(data) > page_size):
            raise LanClientInventoryError("invalid page metadata")
        if total_rows is not None and total != total_rows:
            raise LanClientInventoryError("inconsistent total rows")
        total_rows = total
        rows.extend(data)
        for row in data:
            if not isinstance(row, Mapping) or len(row) > 16:
                invalid += 1
                continue
            unknown += sum(key not in _ROW_FIELDS for key in row)
            if "type" not in row or row["type"] is None:
                missing_type += 1
            elif isinstance(row["type"], str) and row["type"].strip():
                typed += 1
            else:
                invalid += 1
    assert total_rows is not None
    expected_pages = max(1, (total_rows + page_size - 1) // page_size)
    complete = len(pages) == min(expected_pages, max_pages) and len(rows) == min(total_rows, page_size * max_pages)
    if total_rows == 0:
        complete = len(pages) == 1 and not rows
    partial = bool(not complete or invalid or unknown or missing_type)
    type_counts["reported"] = typed
    type_counts["unreported"] = missing_type
    return {
        "status": "ok", "resource": "site_lan_client_inventory_summary",
        "inventory_total_count": total_rows, "returned_count": len(rows),
        "page_count": len(pages), "page_size": page_size,
        "coverage_complete": complete, "type_field_counts": type_counts,
        "invalid_record_count": invalid, "unknown_field_count": unknown,
        "partial": partial,
    }
