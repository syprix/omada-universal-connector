"""Count clients for one selected SSID using its bounded first page."""
from __future__ import annotations

from typing import Any


class SiteSsidClientCountSummaryError(ValueError):
    pass


PAGE_SIZE = 100


def project_ssid_client_count(result: Any, rows: Any) -> dict[str, object]:
    if not isinstance(result, dict) or not isinstance(rows, list) or len(rows) > PAGE_SIZE:
        raise SiteSsidClientCountSummaryError("response_invalid")
    total = result.get("totalRows")
    page = result.get("currentPage")
    size = result.get("currentSize")
    if (type(total) is not int or total < 0 or type(page) is not int or page != 1 or
            type(size) is not int or size not in (len(rows), PAGE_SIZE) or len(rows) > total):
        raise SiteSsidClientCountSummaryError("response_invalid")
    return {
        "status": "ok", "resource": "site_ssid_client_count_summary",
        "client_count": total, "sampled_client_count": len(rows),
        "sample_page": page, "sample_page_size": PAGE_SIZE,
        "coverage_complete": len(rows) == total,
        "client_details_returned": False,
        "online_status_provided": False,
    }
