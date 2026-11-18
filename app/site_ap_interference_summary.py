"""Redacted band counts from the documented top-AP interference lists."""
from __future__ import annotations

from typing import Any


class SiteApInterferenceSummaryError(ValueError):
    """Raised when the documented top-interference result exceeds its bounds."""


_BANDS = {
    "apInterference2g": "2g",
    "apInterference5g": "5g",
    "apInterference5g2": "5g2",
    "apInterference6g": "6g",
}
_ROW_FIELDS = {"name", "mac", "interUtil", "model", "modelVersion", "NearestAp"}
_INT32_MAX = (1 << 31) - 1


def project_site_ap_interference_summary(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 6:
        raise SiteApInterferenceSummaryError("response_invalid")
    data: dict[str, object] = {}
    missing = invalid = 0
    unknown = len(set(result) - set(_BANDS))
    total = 0
    for source, band in _BANDS.items():
        if source not in result:
            missing += 1
            continue
        rows = result[source]
        if not isinstance(rows, list) or len(rows) > 5:
            raise SiteApInterferenceSummaryError("band_rows_invalid")
        data[f"{band}_ap_count"] = len(rows)
        total += len(rows)
        values: list[int] = []
        for row in rows:
            if not isinstance(row, dict) or len(row) > 8:
                invalid += 1
                continue
            unknown += len(set(row) - _ROW_FIELDS)
            value = row.get("interUtil")
            if type(value) is int and 0 <= value <= _INT32_MAX:
                values.append(value)
            elif "interUtil" not in row:
                missing += 1
            else:
                invalid += 1
        if values:
            data[f"{band}_maximum_interference_value"] = max(values)
    data["total_ap_row_count"] = total
    return {"data": data, "missing_field_count": missing,
            "invalid_field_count": invalid, "unknown_field_count": unknown,
            "partial": bool(missing or invalid or unknown)}
