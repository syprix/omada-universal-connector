"""Bounded, identity-free summary of stored site interference scans."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


PAGE_SIZE = 100
MAX_INT32 = 2_147_483_647
MAX_INT64 = 9_223_372_036_854_775_807
_RESULT_FIELDS = {"totalRows", "currentPage", "currentSize", "data", "limit"}
_HISTORY_FIELDS = {
    "historyId", "lastSeen", "scanApNum", "status", "enableInterference",
    "deviceInfoList",
}


class SiteBatchInterferenceHistoryError(ValueError):
    """Raised when the controller history response violates its schema bounds."""


def _integer(value: Any, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def project_site_batch_interference_history(
        result: Any, *, history_ref_for: Callable[[str], str] | None = None
) -> dict[str, object]:
    """Project one documented page without returning history IDs or AP details.

    The three exports declare the same page envelope and history-row fields.
    `lastSeen` has no unit in the schema, so only its presence is counted.
    """
    if result is None:
        result = {}
    if not isinstance(result, dict):
        raise SiteBatchInterferenceHistoryError("response_invalid")
    missing_count = 0
    invalid_count = 0
    unknown_count = len(set(result) - _RESULT_FIELDS)
    partial = bool(unknown_count)

    if "data" not in result:
        data = []
        missing_count += 1
        partial = True
    else:
        data = result["data"]
    if not isinstance(data, list) or len(data) > PAGE_SIZE:
        raise SiteBatchInterferenceHistoryError("response_invalid")

    total_rows = result.get("totalRows")
    if total_rows is None:
        missing_count += 1
        partial = True
    elif not _integer(total_rows, MAX_INT64):
        raise SiteBatchInterferenceHistoryError("response_invalid")

    current_page = result.get("currentPage")
    if current_page is None:
        missing_count += 1
        partial = True
    elif not _integer(current_page, MAX_INT32):
        raise SiteBatchInterferenceHistoryError("response_invalid")
    elif current_page != 1:
        partial = True

    current_size = result.get("currentSize")
    if current_size is None:
        missing_count += 1
        partial = True
    elif not _integer(current_size, MAX_INT32):
        raise SiteBatchInterferenceHistoryError("response_invalid")
    elif current_size != PAGE_SIZE:
        partial = True

    if "limit" in result and not _integer(result["limit"], MAX_INT32):
        raise SiteBatchInterferenceHistoryError("response_invalid")

    scanning_count = 0
    finished_count = 0
    unknown_status_count = 0
    enabled_count = 0
    disabled_count = 0
    unknown_interference_count = 0
    scanned_ap_count = 0
    scanned_ap_reported_count = 0
    last_seen_present_count = 0
    history_refs: list[str] = []

    for row in data:
        if not isinstance(row, dict):
            invalid_count += 1
            partial = True
            continue
        unknown_count += len(set(row) - _HISTORY_FIELDS)
        if set(row) - _HISTORY_FIELDS:
            partial = True

        # Raw IDs are accepted only as opaque schema data and never projected.
        history_id = row.get("historyId")
        if history_id is None:
            missing_count += 1
            partial = True
        elif (not isinstance(history_id, str) or not history_id or
              len(history_id) > 256 or any(ord(char) < 32 for char in history_id)):
            invalid_count += 1
            partial = True
        elif history_ref_for is not None:
            history_refs.append(history_ref_for(history_id))

        status = row.get("status")
        if status is None:
            missing_count += 1
            unknown_status_count += 1
            partial = True
        elif not _integer(status, MAX_INT32):
            invalid_count += 1
            unknown_status_count += 1
            partial = True
        elif status == 0:
            finished_count += 1
        elif status == 1:
            scanning_count += 1
        else:
            unknown_status_count += 1
            partial = True

        last_seen = row.get("lastSeen")
        if last_seen is None:
            missing_count += 1
            partial = True
        elif type(last_seen) is int and -(1 << 63) <= last_seen <= MAX_INT64:
            last_seen_present_count += 1
        else:
            invalid_count += 1
            partial = True

        scan_ap_num = row.get("scanApNum")
        if scan_ap_num is None:
            missing_count += 1
            partial = True
        elif _integer(scan_ap_num, MAX_INT32):
            scanned_ap_count += scan_ap_num
            scanned_ap_reported_count += 1
        else:
            invalid_count += 1
            partial = True

        enabled = row.get("enableInterference")
        if enabled is None:
            missing_count += 1
            unknown_interference_count += 1
            partial = True
        elif type(enabled) is bool:
            if enabled:
                enabled_count += 1
            else:
                disabled_count += 1
        else:
            invalid_count += 1
            unknown_interference_count += 1
            partial = True

        device_info = row.get("deviceInfoList")
        if device_info is not None and not isinstance(device_info, list):
            invalid_count += 1
            partial = True

    returned = len(data)
    has_more = None if total_rows is None else total_rows > returned
    if total_rows is not None and total_rows < returned:
        partial = True

    return {
        "data": {
            "history_count": returned,
            "reported_total_rows": total_rows,
            "scanning_count": scanning_count,
            "finished_count": finished_count,
            "unknown_status_count": unknown_status_count,
            "interference_enabled_count": enabled_count,
            "interference_disabled_count": disabled_count,
            "unknown_interference_count": unknown_interference_count,
            "scanned_ap_count_total": scanned_ap_count,
            "scanned_ap_count_reported": scanned_ap_reported_count,
            "last_seen_present_count": last_seen_present_count,
            "history_refs": history_refs,
            "has_more": has_more,
            "unknown_field_count": unknown_count,
            "invalid_count": invalid_count,
            "missing_count": missing_count,
            "partial": partial,
        }
    }
