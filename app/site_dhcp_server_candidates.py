"""Privacy-preserving summary of devices eligible to serve VLAN DHCP."""

from __future__ import annotations

from collections.abc import Mapping


class SiteDhcpCandidatesError(ValueError):
    """The controller returned an invalid candidate-device page."""


_PAGE_FIELDS = frozenset(("totalRows", "currentPage", "currentSize", "data"))
_MAX_I32 = 2_147_483_647
_MAX_I64 = 9_223_372_036_854_775_807
_PAGE_SIZE = 100
_MAX_PAGES = 5


def project_site_dhcp_candidates(pages: object) -> dict[str, object]:
    """Count eligible devices while discarding their entire source records."""
    if not isinstance(pages, list) or not 1 <= len(pages) <= _MAX_PAGES:
        raise SiteDhcpCandidatesError("pages must be a bounded non-empty list")
    missing = invalid = unknown = returned = valid = page_count = 0
    total_rows: int | None = None
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, Mapping) or len(page) > 16:
            invalid += 1
            continue
        unknown += sum(key not in _PAGE_FIELDS for key in page)
        total = page.get("totalRows")
        if not isinstance(total, int) or isinstance(total, bool) or not 0 <= total <= _MAX_I64:
            if "totalRows" not in page:
                missing += 1
            else:
                invalid += 1
        elif total_rows is None:
            total_rows = total
        elif total != total_rows:
            invalid += 1

        current_page = page.get("currentPage")
        if not isinstance(current_page, int) or isinstance(current_page, bool) or not 1 <= current_page <= _MAX_I32:
            if "currentPage" not in page:
                missing += 1
            else:
                invalid += 1
        elif current_page != index:
            invalid += 1

        current_size = page.get("currentSize")
        if not isinstance(current_size, int) or isinstance(current_size, bool) or not 0 <= current_size <= _PAGE_SIZE:
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
            if not isinstance(row, Mapping) or len(row) > 128:
                invalid += 1
            else:
                valid += 1

    truncated = total_rows is None or returned < total_rows
    if total_rows is not None and returned > total_rows:
        invalid += 1
    if total_rows == 0 and returned != 0:
        invalid += 1
    return {
        "data": {
            "reported_total_candidate_count": total_rows,
            "returned_candidate_count": returned,
            "valid_candidate_record_count": valid,
            "pages_read": page_count,
            "truncated": truncated,
        },
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown or truncated),
    }
