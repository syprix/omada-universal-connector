"""Redacted summary of scheduled controller firmware upgrade plans."""
from __future__ import annotations

from collections.abc import Mapping


class ControllerUpgradePlansError(ValueError):
    pass


def project_controller_upgrade_plans(rows: object, total: object,
                                     pages_fetched: int, page_limit: int) -> dict[str, object]:
    if (not isinstance(rows, list) or len(rows) > 1_000 or type(total) is not int or
            total < len(rows) or not 0 <= total < (1 << 63) or
            type(pages_fetched) is not int or not 0 <= pages_fetched <= 10 or
            type(page_limit) is not int or not 1 <= page_limit <= 10):
        raise ControllerUpgradePlansError("input_invalid")
    present = {"target_version": 0, "scheduled_time": 0, "model_info": 0,
               "site_count": 0, "rollback_flag": 0}
    missing = {key: 0 for key in present}
    version_entries = site_total = 0
    rollback_counts = {"true": 0, "false": 0, "unknown": 0}
    partial = len(rows) < total
    known = {"id", "modelTypeInfo", "siteNames", "siteNum", "currentVersion",
             "targetVersion", "scheduledUpgradeTime", "operator", "fromRollback"}
    for row in rows:
        if not isinstance(row, Mapping) or len(row) > 24:
            raise ControllerUpgradePlansError("row_invalid")
        if set(row) - known:
            partial = True
        for key in ("id", "targetVersion", "scheduledUpgradeTime", "operator"):
            if key in row and (not isinstance(row[key], str) or len(row[key]) > 512):
                raise ControllerUpgradePlansError("field_invalid")
        versions = row.get("currentVersion")
        if versions is not None and (not isinstance(versions, list) or len(versions) > 64 or
                                     any(not isinstance(value, str) or len(value) > 128
                                         for value in versions)):
            raise ControllerUpgradePlansError("field_invalid")
        version_entries += len(versions) if isinstance(versions, list) else 0
        model = row.get("modelTypeInfo")
        if model is not None and (not isinstance(model, Mapping) or len(model) > 4 or
                                  any(not isinstance(model.get(k), str) or len(model[k]) > 256
                                      for k in ("showModel", "compoundModel"))):
            raise ControllerUpgradePlansError("field_invalid")
        site_names = row.get("siteNames")
        if site_names is not None and (not isinstance(site_names, list) or len(site_names) > 20_000 or
                                       any(not isinstance(value, str) or len(value) > 256
                                           for value in site_names)):
            raise ControllerUpgradePlansError("field_invalid")
        site_num = row.get("siteNum")
        if site_num is not None and (type(site_num) is not int or not 0 <= site_num < (1 << 31)):
            raise ControllerUpgradePlansError("field_invalid")
        for key, value in (("target_version", row.get("targetVersion")),
                           ("scheduled_time", row.get("scheduledUpgradeTime")),
                           ("model_info", model), ("site_count", site_num),
                           ("rollback_flag", row.get("fromRollback"))):
            if value is None:
                missing[key] += 1
            else:
                present[key] += 1
        if site_num is not None:
            site_total += site_num
        rollback = row.get("fromRollback")
        if rollback is None:
            rollback_counts["unknown"] += 1
        elif type(rollback) is not bool:
            raise ControllerUpgradePlansError("field_invalid")
        else:
            rollback_counts["true" if rollback else "false"] += 1
        if (versions is None or model is None or site_num is None or
                row.get("targetVersion") is None or row.get("scheduledUpgradeTime") is None or
                rollback is None):
            partial = True
    return {
        "plan_count": len(rows), "total_count": total,
        "coverage_complete": len(rows) >= total,
        "current_version_entry_count": version_entries,
        "site_association_count": site_total,
        "field_presence": {key: {"present": present[key], "missing": missing[key]}
                           for key in present},
        "rollback_origin_counts": rollback_counts,
        "scheduled_time_interpreted": False,
        "execution_started_or_completed_inferred": False,
        "pages_fetched": pages_fetched, "page_limit": page_limit,
        "partial": partial,
        "identifiers_names_versions_models_and_dates_returned": False,
    }
