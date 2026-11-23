"""Redacted projection of the firmware planning model list."""
from __future__ import annotations

from collections.abc import Mapping


class ControllerUpgradeModelListError(ValueError):
    pass


def summarize_upgrade_models(rows: object, reported_total: int, pages_fetched: int,
                             page_limit: int) -> dict[str, object]:
    if (not isinstance(rows, list) or type(reported_total) is not int or reported_total < 0 or
            type(pages_fetched) is not int or pages_fetched < 0 or
            type(page_limit) is not int or page_limit < 1 or len(rows) > 1000):
        raise ControllerUpgradeModelListError("invalid model list")
    status_counts = {"good": 0, "critical": 0, "unknown": 0}
    upgrade_counts = {"up_to_date": 0, "new_version_available": 0, "unknown": 0}
    type_info_rows = current_version_rows = 0
    invalid_rows = invalid_fields = unknown_fields = 0
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 12:
            invalid_rows += 1
            status_counts["unknown"] += 1
            upgrade_counts["unknown"] += 1
            continue
        unknown_fields += sum(key not in {"modelTypeInfo", "currentVersion", "status",
                                          "upgradeStatus"} for key in row)
        info = row.get("modelTypeInfo")
        if isinstance(info, Mapping):
            type_info_rows += 1
            unknown_fields += sum(key not in {"showModel", "compoundModel"} for key in info)
        elif info is not None:
            invalid_fields += 1
        versions = row.get("currentVersion")
        if isinstance(versions, list) and len(versions) <= 256:
            current_version_rows += 1
            if any(not isinstance(version, str) for version in versions):
                invalid_fields += 1
        elif versions is not None:
            invalid_fields += 1
        status = row.get("status")
        if type(status) is int and status in (0, 1):
            status_counts["good" if status == 0 else "critical"] += 1
        elif status is None:
            status_counts["unknown"] += 1
        else:
            invalid_fields += 1
            status_counts["unknown"] += 1
        upgrade = row.get("upgradeStatus")
        if type(upgrade) is int and upgrade in (0, 1):
            upgrade_counts["up_to_date" if upgrade == 0 else "new_version_available"] += 1
        elif upgrade is None:
            upgrade_counts["unknown"] += 1
        else:
            invalid_fields += 1
            upgrade_counts["unknown"] += 1
    return {
        "status": "ok", "resource": "controller_upgrade_model_list_summary",
        "reported_model_count": reported_total, "returned_model_count": len(rows),
        "model_type_info_reported_count": type_info_rows,
        "current_version_field_reported_count": current_version_rows,
        "critical_status_counts": status_counts,
        "upgrade_status_counts": upgrade_counts,
        "pages_fetched": pages_fetched, "page_limit": page_limit,
        "truncated": len(rows) < reported_total,
        "invalid_record_count": invalid_rows, "invalid_field_count": invalid_fields,
        "unknown_field_count": unknown_fields,
        "partial": bool(len(rows) < reported_total or invalid_rows or invalid_fields or
                         unknown_fields or status_counts["unknown"] or
                         upgrade_counts["unknown"]),
    }
