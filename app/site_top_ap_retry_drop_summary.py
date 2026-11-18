"""Redacted counts and ratio peaks from the fixed AP retry/drop ranking."""
from __future__ import annotations

from typing import Any


class SiteTopApRetryDropSummaryError(ValueError):
    """Raised when the documented top-AP response exceeds its bounds."""


_FIELDS = {"device", "model", "modelVersion", "ip", "modelType", "type", "status",
           "health", "mac", "util", "traffic", "ratio", "poePower", "clientCount"}
_LISTS = {"topApByRt": "top_ap_by_rt_count", "topApByDrop": "top_ap_by_drop_count"}


def project_site_top_ap_retry_drop_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 4:
        raise SiteTopApRetryDropSummaryError("response_invalid")
    data: dict[str, object] = {}
    missing = invalid = unknown = 0
    unknown = len(set(result) - set(_LISTS))
    for field, count_name in _LISTS.items():
        if field not in result:
            missing += 1
            continue
        rows = result[field]
        if not isinstance(rows, list) or len(rows) > 5:
            raise SiteTopApRetryDropSummaryError("ranked_rows_invalid")
        data[count_name] = len(rows)
        ratios: list[int] = []
        for row in rows:
            if not isinstance(row, dict) or len(row) > 16:
                invalid += 1
                continue
            unknown += len(set(row) - _FIELDS)
            ratio = row.get("ratio")
            if type(ratio) is int and 0 <= ratio <= 100:
                ratios.append(ratio)
            elif "ratio" not in row:
                missing += 1
            else:
                invalid += 1
        if ratios:
            key = "maximum_ap_by_rt_ratio_percent" if field == "topApByRt" \
                else "maximum_ap_by_drop_ratio_percent"
            data[key] = max(ratios)
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
