"""Redacted aggregation of configured automatic firmware-check plans."""
from __future__ import annotations

from collections.abc import Mapping


class ControllerAutoCheckUpgradeError(ValueError):
    pass


def project_auto_check_upgrades(rows: object, total: object,
                                pages_fetched: int, page_limit: int) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 1_000 or type(total) is not int or
            total < len(rows) or not 0 <= total < (1 << 63) or
            type(pages_fetched) is not int or not 0 <= pages_fetched <= 10 or
            type(page_limit) is not int or not 1 <= page_limit <= 10):
        raise ControllerAutoCheckUpgradeError("input_invalid")

    channels = {"stable": 0, "release_candidate": 0, "beta": 0, "unknown": 0}
    site_associations = 0
    site_count_missing = channel_missing = 0
    partial = len(rows) < total
    known = {"id", "modelTypeInfos", "siteNames", "siteNum", "autoCheckTime",
             "channel", "occurrence"}
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 16:
            raise ControllerAutoCheckUpgradeError("row_invalid")
        if set(row) - known:
            partial = True

        site_num = row.get("siteNum")
        if site_num is None:
            site_count_missing += 1
            partial = True
        elif type(site_num) is not int or not 0 <= site_num < (1 << 31):
            raise ControllerAutoCheckUpgradeError("site_count_invalid")
        else:
            site_associations += site_num
            if site_associations >= (1 << 63):
                raise ControllerAutoCheckUpgradeError("site_count_overflow")

        channel = row.get("channel")
        if channel is None:
            channel_missing += 1
            channels["unknown"] += 1
            partial = True
        elif type(channel) is not int or not 0 <= channel < (1 << 31):
            raise ControllerAutoCheckUpgradeError("channel_invalid")
        else:
            category = {0: "stable", 1: "release_candidate", 2: "beta"}.get(
                channel, "unknown")
            channels[category] += 1
            partial |= category == "unknown"

    return {
        "plan_count": len(rows),
        "total_count": total,
        "coverage_complete": len(rows) >= total,
        "channel_counts": channels,
        "site_association_count": site_associations,
        "site_count_missing_plan_count": site_count_missing,
        "channel_missing_plan_count": channel_missing,
        "pages_fetched": pages_fetched,
        "page_limit": page_limit,
        "partial": partial,
        "schedule_time_and_recurrence_returned": False,
        "update_started_or_firmware_suitability_inferred": False,
        "identifiers_names_models_and_schedule_values_returned": False,
    }
