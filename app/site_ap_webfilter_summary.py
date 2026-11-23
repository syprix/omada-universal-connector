"""Redacted counts for AP URL-filter rules and reported feature flags."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_ROWS = 1_000
SUPPORT_FLAGS = ("supportKeyword", "supportCategory", "supportTimeSchedule")
RULE_FLAGS = ("existKeyword", "existCategory", "existTimeSchedule")
_FIELDS = {
    "id", "index", "type", "name", "status", "policy", "sourceType",
    "sourceIds", "mode", "urls", "keywords", "filterMode", "scenarioMode",
    "categories", "timeRange", *RULE_FLAGS,
}


class SiteApWebfilterSummaryError(ValueError):
    """The API response is outside the documented bounded grid shape."""


def summarize_ap_webfilter_rows(
        rows: object, total_rows: object, omitted_rows: int,
        support_flags: Mapping[str, object]) -> dict[str, Any]:
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or
            type(total_rows) is not int or total_rows < len(rows) or
            type(omitted_rows) is not int or omitted_rows < 0 or
            omitted_rows > max(0, total_rows - len(rows)) or
            not isinstance(support_flags, Mapping)):
        raise SiteApWebfilterSummaryError("input_invalid")

    rule_types = {"ap": 0, "gateway": 0, "unknown": 0}
    filter_modes = {"url": 0, "category": 0, "unknown": 0, "missing": 0}
    status = {"enabled": 0, "disabled": 0, "unknown": 0, "missing": 0}
    row_flags = {name: {"enabled": 0, "disabled": 0, "unknown": 0, "missing": 0}
                 for name in RULE_FLAGS}
    invalid_rows = unknown_fields = 0
    partial = omitted_rows > 0 or total_rows > len(rows) + omitted_rows

    for row in rows:
        if not isinstance(row, Mapping):
            invalid_rows += 1
            rule_types["unknown"] += 1
            filter_modes["unknown"] += 1
            status["unknown"] += 1
            for counts in row_flags.values():
                counts["unknown"] += 1
            partial = True
            continue

        unknown_fields += sum(key not in _FIELDS for key in row)
        if unknown_fields:
            partial = True
        rule_type = row.get("type")
        if type(rule_type) is str and rule_type in ("ap", "gateway"):
            rule_types[rule_type] += 1
        else:
            rule_types["unknown"] += 1
            partial = True

        # The EAP route is AP-specific. A gateway-tagged row is counted as a
        # scope mismatch, but its rule details are not included in AP counts.
        if rule_type != "ap":
            continue

        mode = row.get("filterMode")
        if type(mode) is int and mode in (0, 1):
            filter_modes["url" if mode == 0 else "category"] += 1
        elif "filterMode" not in row:
            filter_modes["missing"] += 1
            partial = True
        else:
            filter_modes["unknown"] += 1
            partial = True

        enabled = row.get("status")
        if type(enabled) is bool:
            status["enabled" if enabled else "disabled"] += 1
        elif "status" not in row:
            status["missing"] += 1
            partial = True
        else:
            status["unknown"] += 1
            partial = True

        for name, counts in row_flags.items():
            value = row.get(name)
            if type(value) is bool:
                counts["enabled" if value else "disabled"] += 1
            elif name not in row:
                counts["missing"] += 1
                partial = True
            else:
                counts["unknown"] += 1
                partial = True

    reported_support = {}
    for field in SUPPORT_FLAGS:
        value = support_flags.get(field)
        counts = {"supported": 0, "unsupported": 0, "unknown": 0,
                  "missing": 0, "inconsistent": 0}
        if value is True:
            counts["supported"] = 1
        elif value is False:
            counts["unsupported"] = 1
        elif value == "inconsistent":
            counts["inconsistent"] = 1
            partial = True
        elif field not in support_flags:
            counts["missing"] = 1
            partial = True
        else:
            counts["unknown"] = 1
            partial = True
        reported_support[field] = counts

    if rule_types["gateway"] or rule_types["unknown"]:
        partial = True
    partial = partial or bool(invalid_rows or unknown_fields)
    return {
        "status": "partial" if partial else "ok",
        "resource": "site_ap_webfilter_summary",
        "reported_rule_total": total_rows,
        "returned_rule_count": len(rows),
        "omitted_rule_count": omitted_rows,
        "by_documented_endpoint_rule_type": rule_types,
        "by_documented_ap_filter_mode": filter_modes,
        "reported_ap_rule_status": status,
        "ap_rule_feature_flag_coverage": row_flags,
        "reported_feature_support": reported_support,
        "invalid_row_count": invalid_rows,
        "unknown_field_count": unknown_fields,
        "partial": partial,
        "raw_rules_urls_keywords_categories_schedules_and_sources_returned": False,
        "enforcement_inferred": False,
    }
