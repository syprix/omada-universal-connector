"""Redacted counts for switch LAN profile assignments."""
from __future__ import annotations
from collections.abc import Mapping

class LanSwitchProfileError(ValueError):
    pass

def project_lan_switch_profile_page(payload: object, expected_page: int, page_size: int, max_rows: int | None = None) -> dict[str, object]:
    # getOswPortLanNetInfo documents a direct GridVO response, unlike the
    # OperationResponse wrappers used by other endpoints.
    if not isinstance(payload, Mapping) or set(payload) - {"totalRows", "currentPage", "currentSize", "data"}:
        raise LanSwitchProfileError("envelope_invalid")
    total, page, size, rows = (payload.get(k) for k in ("totalRows", "currentPage", "currentSize", "data"))
    if (type(total) is not int or not 0 <= total < (1 << 63) or
        type(page) is not int or page != expected_page or
        type(size) is not int or not 0 <= size <= page_size or
        not isinstance(rows, list) or len(rows) > page_size or size not in (len(rows), page_size)):
        raise LanSwitchProfileError("grid_invalid")
    selected_rows = rows if max_rows is None else rows[:max(0, max_rows)]
    assignments = known = unknown = 0
    for row in selected_rows:
        if not isinstance(row, Mapping) or set(row) - {"name", "mac", "profiles"}:
            raise LanSwitchProfileError("row_invalid")
        for key in ("name", "mac"):
            if key in row and (not isinstance(row[key], str) or len(row[key]) > 512):
                raise LanSwitchProfileError("row_invalid")
        profiles = row.get("profiles")
        if profiles is None:
            unknown += 1
            continue
        if not isinstance(profiles, Mapping) or len(profiles) > 512:
            raise LanSwitchProfileError("profiles_invalid")
        if any(not isinstance(k, str) or len(k) > 256 or not isinstance(v, str) or len(v) > 512
               for k, v in profiles.items()):
            raise LanSwitchProfileError("profiles_invalid")
        assignments += len(profiles)
        known += 1
    return {"total_rows": total, "rows": len(selected_rows), "profile_assignments": assignments,
            "rows_with_profile_data": known, "rows_without_profile_data": unknown}
