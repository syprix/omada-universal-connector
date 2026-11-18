"""Bounded projection for paged site anomaly event settings."""
from __future__ import annotations

from typing import Any


MAX_ROWS = 100
MAX_INT32 = 2_147_483_647
MAX_INT64 = 9_223_372_036_854_775_807
LEVEL_CODES = frozenset({0, 1, 2, 3})
CATEGORY_CODES = frozenset({0, 1, 2, 3, 4, 5, 6, 7, 8, 9,
                            11, 12, 13, 14, 15, 16, 17, 18, 19})
OBJECT_TYPES = frozenset({"gateway", "switch", "ap", "wiredClient", "wirelessClient"})
STAT_FIELDS = ("all", "enable", "disable", "allLevel", "critical", "error",
               "warning", "info")


class SiteAnomalyEventSettingsError(ValueError):
    """Raised when the response envelope cannot be safely projected."""


def project_site_anomaly_event_settings(result: Any) -> dict[str, object]:
    """Keep bounded event codes and flags; discard arbitrary parameters and labels."""
    if not isinstance(result, dict) or len(result) > 12:
        raise SiteAnomalyEventSettingsError("response_invalid")
    counts = {"invalid_count": 0, "unknown_field_count": 0,
              "omitted_parameter_count": 0}
    data: dict[str, object] = {}
    allowed_top = {"totalRows", "currentPage", "currentSize", "data", "resource", "statistic"}
    counts["unknown_field_count"] += len(set(result) - allowed_top)

    for source, target, maximum in (("totalRows", "total_rows", MAX_INT64),
                                    ("currentPage", "current_page", MAX_INT32),
                                    ("currentSize", "current_size", MAX_INT32),
                                    ("resource", "resource_code", 2)):
        if source in result:
            value = result[source]
            minimum = 1 if source in {"currentPage", "currentSize"} else 0
            if type(value) is int and minimum <= value <= maximum:
                data[target] = value
            else:
                counts["invalid_count"] += 1

    rows = result.get("data")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        counts["invalid_count"] += 1
        rows = []
    items: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict) or len(row) > 12:
            counts["invalid_count"] += 1
            continue
        allowed = {"anomalyCode", "category", "enable", "level", "objectType", "params"}
        counts["unknown_field_count"] += len(set(row) - allowed)
        item: dict[str, object] = {}

        code = row.get("anomalyCode")
        if isinstance(code, str) and 1 <= len(code) <= 32 and code.isascii() and code.isalnum():
            item["anomaly_code"] = code
        else:
            counts["invalid_count"] += 1
        if "category" in row:
            category = row["category"]
            if type(category) is int and category in CATEGORY_CODES:
                item["category_code"] = category
            else:
                counts["invalid_count"] += 1
        if "enable" in row:
            enabled = row["enable"]
            if type(enabled) is bool:
                item["enabled"] = enabled
            else:
                counts["invalid_count"] += 1
        if "level" in row:
            level = row["level"]
            if type(level) is int and level in LEVEL_CODES:
                item["level_code"] = level
            else:
                counts["invalid_count"] += 1
        if "objectType" in row:
            object_type = row["objectType"]
            if isinstance(object_type, str) and object_type in OBJECT_TYPES:
                item["object_type"] = object_type
            else:
                counts["unknown_field_count"] += 1
        if "params" in row:
            params = row["params"]
            if not isinstance(params, dict) or len(params) > 32:
                counts["invalid_count"] += 1
            else:
                valid_params = 0
                for key, value in params.items():
                    if (isinstance(key, str) and 1 <= len(key) <= 64 and key.isascii() and
                            type(value) is int and -MAX_INT32 - 1 <= value <= MAX_INT32):
                        valid_params += 1
                    else:
                        counts["invalid_count"] += 1
                counts["omitted_parameter_count"] += valid_params
        items.append(item)
    data["items"] = items
    data["returned_count"] = len(items)

    if "total_rows" in data:
        data["has_more"] = data["total_rows"] > len(items)
        if data["has_more"]:
            counts["omitted_row_count"] = max(0, data["total_rows"] - len(items))
    else:
        data["has_more"] = None

    if "statistic" in result:
        statistic = result["statistic"]
        if not isinstance(statistic, dict) or len(statistic) > len(STAT_FIELDS):
            counts["invalid_count"] += 1
        else:
            counts["unknown_field_count"] += len(set(statistic) - set(STAT_FIELDS))
            safe_stats: dict[str, int] = {}
            for field in STAT_FIELDS:
                if field not in statistic:
                    counts["invalid_count"] += 1
                elif (type(statistic[field]) is int and
                      0 <= statistic[field] <= MAX_INT32):
                    safe_stats[field] = statistic[field]
                else:
                    counts["invalid_count"] += 1
            data["statistics"] = safe_stats

    counts["omitted_parameter_count"] = counts.get("omitted_parameter_count", 0)
    counts["omitted_row_count"] = counts.get("omitted_row_count", 0)
    data.update(counts)
    present_count = sum(key in data for key in (
        "total_rows", "current_page", "current_size", "resource_code", "statistics"))
    data["present_count"] = present_count
    return {"data": data,
            "partial": bool(counts["invalid_count"] or counts["unknown_field_count"] or
                             counts["omitted_parameter_count"] or counts["omitted_row_count"])}
