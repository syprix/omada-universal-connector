"""Privacy-preserving summary of the documented virtual WAN grid."""

from __future__ import annotations

from collections.abc import Mapping


class SiteVirtualWanError(ValueError):
    """The controller response does not satisfy the bounded grid contract."""


def project_virtual_wan_pages(
        pages: list[object], available_rows: object, *, page_size: int = 100) -> dict[str, object]:
    """Summarize virtual WAN configuration and its availability list.

    ``id`` and ``virtualWanId`` are both documented as the virtual WAN ID, so
    those rows can be joined when each key is unique. The exports do not define
    a crosswalk to physical port configuration or runtime WAN status.
    """
    if not isinstance(pages, list) or not 1 <= len(pages) <= 10:
        raise SiteVirtualWanError("pages must be a bounded non-empty list")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
        raise SiteVirtualWanError("page_size is invalid")
    if not isinstance(available_rows, list) or len(available_rows) > 1000:
        raise SiteVirtualWanError("available_rows must be a bounded list")

    total_rows: int | None = None
    rows_seen = 0
    enabled = disabled = missing_status = 0
    missing_physical_id = missing_physical_port = 0
    invalid_rows = invalid_pages = 0
    inventory_ids: list[str | None] = []
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
            virtual_id = row.get("id")
            inventory_ids.append(virtual_id if isinstance(virtual_id, str) and virtual_id else None)

    available_ids: list[str | None] = []
    invalid_availability_rows = 0
    for row in available_rows:
        if not isinstance(row, Mapping) or len(row) > 16:
            invalid_availability_rows += 1
            available_ids.append(None)
            continue
        virtual_id = row.get("virtualWanId")
        available_ids.append(virtual_id if isinstance(virtual_id, str) and virtual_id else None)

    if invalid_pages or total_rows is None or rows_seen > total_rows:
        raise SiteVirtualWanError("grid pages are inconsistent")
    complete = rows_seen == total_rows and invalid_rows == 0
    inventory_counts: dict[str, int] = {}
    availability_counts: dict[str, int] = {}
    for virtual_id in inventory_ids:
        if virtual_id is not None:
            inventory_counts[virtual_id] = inventory_counts.get(virtual_id, 0) + 1
    for virtual_id in available_ids:
        if virtual_id is not None:
            availability_counts[virtual_id] = availability_counts.get(virtual_id, 0) + 1
    ambiguous_ids = {virtual_id for virtual_id, count in inventory_counts.items() if count > 1}
    ambiguous_ids.update(virtual_id for virtual_id, count in availability_counts.items() if count > 1)
    ambiguous = len(ambiguous_ids)
    matched = sum(1 for virtual_id, count in inventory_counts.items()
                  if count == 1 and availability_counts.get(virtual_id) == 1)
    unmatched_inventory = sum(
        1 for virtual_id in inventory_ids
        if virtual_id is None or inventory_counts.get(virtual_id) != 1 or
        availability_counts.get(virtual_id) != 1)
    unmatched_availability = sum(
        1 for virtual_id in available_ids
        if virtual_id is None or availability_counts.get(virtual_id) != 1 or
        inventory_counts.get(virtual_id) != 1)
    join_complete = (complete and invalid_availability_rows == 0 and ambiguous == 0 and
                     None not in inventory_ids and None not in available_ids)
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
        "availability_row_count": len(available_rows),
        "matched_virtual_wan_count": matched,
        "unmatched_inventory_count": unmatched_inventory,
        "unmatched_availability_count": unmatched_availability,
        "ambiguous_join_key_count": ambiguous,
        "unkeyed_inventory_count": inventory_ids.count(None),
        "unkeyed_availability_count": available_ids.count(None),
        "invalid_availability_row_count": invalid_availability_rows,
        "availability_complete": invalid_availability_rows == 0,
        "virtual_availability_join": "unique_documented_virtual_wan_id",
        "join_complete": join_complete,
        "physical_join": "not_defined_by_source_contract",
    }
