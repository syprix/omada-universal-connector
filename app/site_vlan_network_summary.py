"""Privacy-preserving, bounded summary of the site's VLAN network list."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping


class SiteVlanNetworkError(ValueError):
    """The controller returned an invalid VLAN-network page."""


_PAGE_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_ROW_FIELDS = frozenset(("name", "id", "vlan", "purpose"))
_MAX_I32 = 2_147_483_647
_MAX_I64 = 9_223_372_036_854_775_807
_PAGE_SIZE = 100
_MAX_PAGES = 5


def project_site_vlan_networks(pages: object) -> dict[str, object]:
    """Summarize up to 500 rows without returning network names, IDs or VLAN IDs."""
    if not isinstance(pages, list) or not 1 <= len(pages) <= _MAX_PAGES:
        raise SiteVlanNetworkError("pages must be a bounded non-empty list")
    missing = invalid = unknown = returned = 0
    purpose_counts: Counter[str] = Counter()
    vlans: set[int] = set()
    reported_total: int | None = None
    page_count = 0

    for index, page in enumerate(pages, start=1):
        if not isinstance(page, Mapping) or len(page) > 16:
            invalid += 1
            continue
        unknown += sum(key not in _PAGE_FIELDS for key in page)
        total = page.get("totalRows")
        if (not isinstance(total, int) or isinstance(total, bool) or
                not 0 <= total <= _MAX_I64):
            if "totalRows" not in page:
                missing += 1
            else:
                invalid += 1
            total = None
        elif reported_total is None:
            reported_total = total
        elif total != reported_total:
            invalid += 1

        current_page = page.get("currentPage")
        if (not isinstance(current_page, int) or isinstance(current_page, bool) or
                not 1 <= current_page <= _MAX_I32):
            if "currentPage" not in page:
                missing += 1
            else:
                invalid += 1
        elif current_page != index:
            invalid += 1

        current_size = page.get("currentSize")
        if (not isinstance(current_size, int) or isinstance(current_size, bool) or
                not 0 <= current_size <= _PAGE_SIZE):
            if "currentSize" not in page:
                missing += 1
            else:
                invalid += 1

        rows = page.get("data")
        if not isinstance(rows, list) or len(rows) > _PAGE_SIZE:
            if "data" not in page:
                missing += 1
            else:
                invalid += 1
            continue
        page_count += 1
        returned += len(rows)
        if isinstance(current_size, int) and not isinstance(current_size, bool) and current_size != len(rows):
            invalid += 1
        for row in rows:
            if not isinstance(row, Mapping) or len(row) > 16:
                invalid += 1
                continue
            unknown += sum(key not in _ROW_FIELDS for key in row)
            purpose = row.get("purpose")
            if not isinstance(purpose, str) or not purpose:
                if "purpose" not in row:
                    missing += 1
                else:
                    invalid += 1
            else:
                purpose_counts[purpose] += 1
            if "vlan" in row:
                vlan = row["vlan"]
                if (not isinstance(vlan, int) or isinstance(vlan, bool) or
                        not -(2**31) <= vlan <= _MAX_I32):
                    invalid += 1
                else:
                    vlans.add(vlan)
            for optional_name in ("name", "id"):
                if optional_name in row and not isinstance(row[optional_name], str):
                    invalid += 1

    truncated = reported_total is None or returned < reported_total
    if reported_total is not None and returned > reported_total:
        invalid += 1
    if reported_total == 0 and returned != 0:
        invalid += 1
    return {
        "data": {
            "reported_total_row_count": reported_total,
            "returned_row_count": returned,
            "distinct_vlan_id_count": len(vlans),
            "purpose_code_counts": dict(sorted(purpose_counts.items())),
            "pages_read": page_count,
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or truncated),
    }
