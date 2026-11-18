"""Small, identity-free projections for WLAN/AP group capacity reads."""
from __future__ import annotations

from typing import Any


MAX_INT64 = 9_223_372_036_854_775_807


class SiteWirelessGroupCapacityError(ValueError):
    """Raised when a group-capacity response cannot be projected safely."""


def project_site_wireless_group_capacity(result: Any, count_field: str) -> dict[str, object]:
    if count_field not in {"wlanGroupNum", "apGroupNum"}:
        raise SiteWirelessGroupCapacityError("count_field_invalid")
    if not isinstance(result, dict) or len(result) > 4:
        raise SiteWirelessGroupCapacityError("response_invalid")
    counts = {"invalid_count": 0, "unknown_field_count": 0}
    data: dict[str, object] = {}
    allowed = {count_field, "exceeded"}
    counts["unknown_field_count"] += len(set(result) - allowed)
    if count_field in result:
        count = result[count_field]
        if type(count) is int and 0 <= count <= MAX_INT64:
            data["group_count"] = count
        else:
            counts["invalid_count"] += 1
    else:
        counts["invalid_count"] += 1
    if "exceeded" in result:
        if type(result["exceeded"]) is bool:
            data["limit_exceeded"] = result["exceeded"]
        else:
            counts["invalid_count"] += 1
    else:
        counts["invalid_count"] += 1
    data.update(counts)
    data["present_count"] = sum(key in data for key in ("group_count", "limit_exceeded"))
    return {"data": data, "partial": bool(counts["invalid_count"] or counts["unknown_field_count"])}
