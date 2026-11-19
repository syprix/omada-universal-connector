"""Privacy-preserving summary of the documented virtual WAN grid."""

from __future__ import annotations

from collections.abc import Mapping


class SiteVirtualWanError(ValueError):
    """The controller response does not satisfy the bounded grid contract."""


def project_virtual_wan_pages(pages: list[object], *, page_size: int = 100) -> dict[str, object]:
    """Summarize status and documented physical references without exposing IDs.

    The API exports do not define a key that crosswalks ``physicalWanId`` to
    ``wanPortsConfig.portId`` or the runtime WAN ``port`` field. This projection
    therefore reports independent counts and never implies a physical match.
    """
    if not isinstance(pages, list) or not 1 <= len(pages) <= 10:
        raise SiteVirtualWanError("pages must be a bounded non-empty list")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
        raise SiteVirtualWanError("page_size is invalid")

    total_rows: int | None = None
    rows_seen = 0
    enabled = disabled = missing_status = 0
    missing_physical_id = missing_physical_port = 0
    invalid_rows = invalid_pages = 0
    for expected_page, page in enumerate(pages, start=1):
        if not isinstance(page, Mapping) or len(page) > 24:
            invalid_pages += 1
            continue
        total = page.get("totalRows")
        current = page.get("currentPage")
        current_size = page.get("currentSize")
        data = page.get("data")
        if (isinstance(total, bool) or not isinstance(total, int) or total < 0 or
                isinstance(current, bool) or not isinstance(current, int) or current != expected_page or
                isinstance(current_size, bool) or not isinstance(current_size, int) or
                not isinstance(data, list) or len(data) > page_size or current_size != len(data)):
            invalid_pages += 1
            continue
        if total_rows is None:
            total_rows = total
        elif total_rows != total:
            invalid_pages += 1
            continue
        rows_seen += len(data)
        for row in data:
            if not isinstance(row, Mapping) or len(row) > 32:
                invalid_rows += 1
                continue
            status = row.get("status")
            if isinstance(status, bool):
                enabled += int(status)
                disabled += int(not status)
            else:
                missing_status += 1
            physical_id = row.get("physicalWanId")
            if not isinstance(physical_id, str) or not physical_id:
                missing_physical_id += 1
            physical_port_id = row.get("physicalWanPortId")
            if isinstance(physical_port_id, bool) or not isinstance(physical_port_id, int):
                missing_physical_port += 1

    if invalid_pages or total_rows is None or rows_seen > total_rows:
        raise SiteVirtualWanError("grid pages are inconsistent")
    complete = rows_seen == total_rows and invalid_rows == 0
    return {
        "virtual_wan_count": rows_seen,
        "declared_total": total_rows,
        "enabled_count": enabled,
        "disabled_count": disabled,
        "missing_status_count": missing_status,
        "missing_physical_wan_id_count": missing_physical_id,
        "missing_physical_wan_port_id_count": missing_physical_port,
        "invalid_row_count": invalid_rows,
        "complete": complete,
        "physical_join": "not_defined_by_source_contract",
    }
