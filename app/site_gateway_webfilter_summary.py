"""Redacted bounded summary for gateway URL-filter rules."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_ROWS = 1000
RULE_TYPES = {"gateway", "ap"}
RULE_FLAGS = ("existKeyword", "existCategory", "existTimeSchedule")
SUPPORT_FLAGS = ("supportKeyword", "supportCategory", "supportTimeSchedule")


def summarize_gateway_webfilter_result(
    result: object, *, omitted_rows: int = 0,
) -> dict[str, Any]:
    if (not isinstance(result, Mapping) or type(omitted_rows) is not int or
            omitted_rows < 0):
        raise ValueError("invalid webfilter result")
    rows = result.get("data")
    total = result.get("totalRows")
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS or type(total) is not int or
            total < len(rows) or omitted_rows > max(0, total - len(rows))):
        raise ValueError("invalid webfilter grid")

    by_type = {rule_type: 0 for rule_type in sorted(RULE_TYPES)}
    status = {"enabled": 0, "disabled": 0, "unknown": 0, "missing": 0}
    flag_coverage = {
        name: {"enabled": 0, "disabled": 0, "unknown": 0, "missing": 0}
        for name in RULE_FLAGS
    }
    unknown_type_count = 0
    invalid_row_count = 0

    for row in rows:
        if not isinstance(row, Mapping):
            invalid_row_count += 1
            status["unknown"] += 1
            for counts in flag_coverage.values():
                counts["unknown"] += 1
            unknown_type_count += 1
            continue
        rule_type = row.get("type")
        if isinstance(rule_type, str) and rule_type in RULE_TYPES:
            by_type[rule_type] += 1
        else:
            unknown_type_count += 1

        enabled = row.get("status")
        if "status" not in row:
            status["missing"] += 1
        elif type(enabled) is not bool:
            status["unknown"] += 1
        else:
            status["enabled" if enabled else "disabled"] += 1

        for field, counts in flag_coverage.items():
            value = row.get(field)
            if field not in row:
                counts["missing"] += 1
            elif type(value) is not bool:
                counts["unknown"] += 1
            else:
                counts["enabled" if value else "disabled"] += 1

    support_flags: dict[str, dict[str, int]] = {}
    for field in SUPPORT_FLAGS:
        value = result.get(field)
        counts = {"supported": 0, "unsupported": 0, "unknown": 0, "missing": 0}
        if field not in result:
            counts["missing"] = 1
        elif type(value) is not bool:
            counts["unknown"] = 1
        else:
            counts["supported" if value else "unsupported"] = 1
        support_flags[field] = counts

    unreported = max(0, total - len(rows) - omitted_rows)
    return {
        "summarized_rule_count": len(rows),
        "source_total_rule_count": total,
        "omitted_rule_count": omitted_rows,
        "unreported_rule_count": unreported,
        "by_documented_rule_type": by_type,
        "unknown_rule_type_count": unknown_type_count,
        "enabled_status_count": status["enabled"],
        "disabled_status_count": status["disabled"],
        "unknown_status_count": status["unknown"],
        "missing_status_count": status["missing"],
        "rule_feature_flag_coverage": flag_coverage,
        "source_feature_support": support_flags,
        "invalid_row_count": invalid_row_count,
        "partial": bool(omitted_rows or unreported or invalid_row_count or
                         unknown_type_count or status["unknown"] or
                         status["missing"] or any(
                             counts["unknown"] or counts["missing"]
                             for counts in flag_coverage.values()) or any(
                             count["unknown"] or count["missing"]
                             for count in support_flags.values())),
        "configuration_only": True,
    }
