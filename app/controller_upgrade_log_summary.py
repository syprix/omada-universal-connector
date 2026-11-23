"""Bounded aggregate of documented controller firmware-upgrade logs."""
from __future__ import annotations

from typing import Any


class ControllerUpgradeLogSummaryError(ValueError):
    pass


PAGE_SIZE = 100
ALLOWED_FIELDS = {
    "id", "modelTypeInfo", "siteNames", "siteNum", "currentVersion",
    "targetVersion", "upgradeTime", "operator", "rollbacked", "failedDeviceNum",
}


def summarize_upgrade_log_page(result: Any, rows: Any) -> dict[str, object]:
    if not isinstance(result, dict) or not isinstance(rows, list) or len(rows) > PAGE_SIZE:
        raise ControllerUpgradeLogSummaryError("response_invalid")
    total, page, size = result.get("totalRows"), result.get("currentPage"), result.get("currentSize")
    if (type(total) is not int or total < 0 or type(page) is not int or page != 1 or
            type(size) is not int or size not in (len(rows), PAGE_SIZE) or len(rows) > total):
        raise ControllerUpgradeLogSummaryError("response_invalid")
    rollbacked = {"true": 0, "false": 0}
    rollbacked_missing = failed_missing = time_missing = invalid = unknown = with_failures = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            invalid += 1
            continue
        unknown += len(set(row) - ALLOWED_FIELDS)
        value = row.get("rollbacked")
        if isinstance(value, bool):
            rollbacked[str(value).lower()] += 1
        else:
            rollbacked_missing += 1
            if value is not None:
                invalid += 1
        failed = row.get("failedDeviceNum")
        if type(failed) is int and 0 <= failed <= 2**31 - 1:
            with_failures += failed > 0
        else:
            failed_missing += 1
            if failed is not None:
                invalid += 1
        upgrade_time = row.get("upgradeTime")
        if isinstance(upgrade_time, str):
            if not upgrade_time:
                time_missing += 1
        else:
            time_missing += 1
            if upgrade_time is not None:
                invalid += 1
    return {
        "status": "ok", "resource": "controller_upgrade_log_summary",
        "source_total_rows": total, "sampled_log_count": len(rows),
        "sample_page": 1, "sample_page_size": PAGE_SIZE,
        "coverage_complete": len(rows) == total,
        "rollbacked_counts": rollbacked,
        "logs_with_failed_devices_count": with_failures,
        "rollbacked_missing_count": rollbacked_missing,
        "failed_device_count_missing": failed_missing,
        "upgrade_time_missing_count": time_missing,
        "invalid_row_count": invalid, "unknown_field_count": unknown,
        "partial": bool(rollbacked_missing or failed_missing or time_missing or invalid or unknown),
        "identities_and_versions_returned": False,
    }
