"""Redacted, bounded counts from the documented known-client time filter."""
from __future__ import annotations

from typing import Any


class SiteRecentClientsError(ValueError):
    """Malformed request or known-client page."""


_MAX_WINDOW_MS = 24 * 60 * 60 * 1000
_MAX_PAGE_SIZE = 100
_MAX_TIME_MS = (1 << 63) - 1


def project_site_recent_clients(result: Any, start_ms: int, end_ms: int,
                                page_size: int) -> dict[str, object]:
    if (type(start_ms) is not int or type(end_ms) is not int or
            not 0 <= start_ms < end_ms <= _MAX_TIME_MS or
            end_ms - start_ms > _MAX_WINDOW_MS or
            type(page_size) is not int or not 1 <= page_size <= _MAX_PAGE_SIZE):
        raise SiteRecentClientsError("request_invalid")
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteRecentClientsError("response_invalid")
    rows = result.get("data")
    if not isinstance(rows, list) or len(rows) > page_size:
        raise SiteRecentClientsError("response_invalid")
    total = result.get("totalRows")
    page = result.get("currentPage")
    size = result.get("currentSize")
    if (type(total) is not int or total < 0 or type(page) is not int or page != 1 or
            type(size) is not int or not len(rows) <= size <= page_size or
            (total == 0 and rows) or (total > 0 and not rows)):
        raise SiteRecentClientsError("response_invalid")
    # lastSeen is documented as an integer but its unit is not specified. Do not
    # interpret it; the timeStart/timeEnd source filters themselves are in ms.
    malformed = sum(not isinstance(row, dict) for row in rows)
    return {
        "window_start_ms": start_ms,
        "window_end_ms": end_ms,
        "reported_client_count": total,
        "sampled_row_count": len(rows) - malformed,
        "invalid_row_count": malformed,
        "page_size": page_size,
        "has_more": total > len(rows),
        "time_filter_applied_by_controller": True,
        "last_seen_unit_interpreted": False,
        "partial": total > len(rows) or bool(malformed),
        "no_absence_or_outage_inference": True,
    }
