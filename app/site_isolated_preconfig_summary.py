"""Counts from the documented isolated and preconfigured device lists."""
from __future__ import annotations

from collections.abc import Mapping


class IsolatedPreconfigError(ValueError):
    pass


_FIELDS = frozenset(("type", "mac", "name", "model", "modelVersion",
                     "healthScore", "ippt"))


def summarize_isolated_preconfig(value: object, *, max_items: int = 1000
                                 ) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > 8 or type(max_items) is not int or max_items < 1:
        raise IsolatedPreconfigError("invalid summary envelope")
    result_total = value.get("total")
    if type(result_total) is not int or result_total < 0:
        raise IsolatedPreconfigError("invalid total")
    categories: dict[str, object] = {}
    invalid = unknown = invalid_fields = 0
    for source, output in (("isolated", "isolated"), ("preconfig", "preconfigured")):
        rows = value.get(source)
        if not isinstance(rows, list):
            raise IsolatedPreconfigError("invalid category list")
        visible = rows[:max_items]
        row_type_reported = health_reported = 0
        ippt = {"enabled": 0, "disabled": 0, "unreported": 0}
        unknown_field_count = 0
        invalid_count = 0
        for row in visible:
            if not isinstance(row, Mapping) or len(row) > 16:
                invalid_count += 1
                continue
            unknown_field_count += sum(key not in _FIELDS for key in row)
            if isinstance(row.get("type"), str) and row["type"].strip():
                row_type_reported += 1
            if "healthScore" in row:
                if type(row["healthScore"]) is int:
                    health_reported += 1
                else:
                    invalid_fields += 1
            flag = row.get("ippt")
            if flag is None:
                ippt["unreported"] += 1
            elif type(flag) is bool:
                ippt["enabled" if flag else "disabled"] += 1
            else:
                ippt["unreported"] += 1
                invalid_fields += 1
        invalid += invalid_count
        unknown += unknown_field_count
        categories[output] = {
            "reported_count": len(rows), "returned_count": len(visible),
            "device_type_reported_count": row_type_reported,
            "device_type_unreported_count": len(visible) - invalid_count - row_type_reported,
            "health_score_reported_count": health_reported,
            "ippt_flag_counts": ippt,
            "invalid_record_count": invalid_count,
            "unknown_field_count": unknown_field_count,
            "truncated": len(rows) > max_items,
        }
    total_mismatch = result_total != sum(
        categories[key]["reported_count"] for key in categories)
    return {
        "status": "ok", "resource": "site_isolated_preconfig_summary",
        "reported_total": result_total,
        "category_reported_total": sum(categories[key]["reported_count"] for key in categories),
        "categories": categories, "total_mismatch": total_mismatch,
        "invalid_record_count": invalid, "invalid_field_count": invalid_fields,
        "unknown_field_count": unknown,
        "partial": bool(total_mismatch or invalid or invalid_fields or
                         unknown or any(categories[k]["truncated"] for k in categories)),
    }
