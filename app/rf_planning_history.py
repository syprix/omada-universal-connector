"""Bounded, redacted list of stored WLAN optimization history records."""
from __future__ import annotations

from collections.abc import Callable
import re

class RfPlanningHistoryError(ValueError):
    """The history response is malformed or outside safe result bounds."""

    def __init__(self, code: str = "rf_planning_history_invalid") -> None:
        super().__init__(code)
        self.code = code


_MAX_FIELDS = 32
_MAX_ROWS = 100
_MAX_KEY_LENGTH = 128
_INT64_MAX = 2**63 - 1
_INT32_MAX = 2**31 - 1
_RECORD_FIELDS = {
    "time": ("time_ms", "int64"),
    "channelDeployEnable": ("channel_deploy_enabled", "bool"),
    "channelWidthDeployEnable": ("channel_width_deploy_enabled", "bool"),
    "powerAdjustEnable": ("power_adjust_enabled", "bool"),
    "bandDeployEnable": ("band_deploy_enabled", "bool"),
    "beforeIndex": ("before_index", "index"),
    "afterIndex": ("after_index", "index"),
    "apNum": ("ap_count", "nonnegative_int32"),
    "length": ("duration_seconds", "nonnegative_int32"),
    "mode": ("mode", "mode"),
    "isScanSuccess": ("scan_success", "bool"),
    "isAppliedSuccess": ("applied_success", "bool"),
    "currentConfig": ("current_config", "current_config"),
    "msgType": ("message_type", "int32"),
}
_REDACTED_FIELDS = {"planningHistroyId", "msg", "failedMacs2g", "failedMacs5g", "failedMacs6g"}


def _check_keys(raw: dict[object, object]) -> None:
    if len(raw) > _MAX_FIELDS or any(not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH
                                     for key in raw):
        raise RfPlanningHistoryError()


def _valid(value: object, kind: str) -> bool:
    if kind == "bool":
        return type(value) is bool
    if kind == "int64":
        return type(value) is int and 0 <= value <= _INT64_MAX
    if kind == "index":
        return type(value) is int and 0 <= value <= 100
    if kind == "nonnegative_int32":
        return type(value) is int and 0 <= value <= _INT32_MAX
    if kind == "positive_int32":
        return type(value) is int and 1 <= value <= _INT32_MAX
    if kind == "mode":
        return type(value) is int and value in (0, 1)
    if kind == "current_config":
        return type(value) is int and value in (0, 1, 2)
    return type(value) is int and -_INT32_MAX <= value <= _INT32_MAX


def project_rf_planning_history(raw: object, *, start_ms: int | None = None,
                                end_ms: int | None = None,
                                history_ref_for_id: Callable[[str], str] | None = None
                                ) -> dict[str, object]:
    """Project one bounded page; remove history IDs, messages and MAC lists."""
    if not isinstance(raw, dict):
        raise RfPlanningHistoryError()
    if ((start_ms is None) != (end_ms is None) or
            (start_ms is not None and (type(start_ms) is not int or type(end_ms) is not int or
                                       start_ms < 0 or end_ms < start_ms or end_ms > _INT64_MAX))):
        raise RfPlanningHistoryError()
    _check_keys(raw)
    missing: list[str] = []
    omitted: set[str] = set()
    omitted_count = 0
    redacted_count = 0
    data: dict[str, object] = {}
    total_rows: int | None = None
    for source, target, kind in (("totalRows", "total_count", "int64"),
                                 ("currentPage", "page", "positive_int32"),
                                 ("currentSize", "page_size", "positive_int32")):
        if source not in raw:
            missing.append(source)
        elif _valid(raw[source], kind):
            data[target] = raw[source]
            if source == "totalRows":
                total_rows = raw[source]
        else:
            omitted.add("invalid_pagination")
            omitted_count += 1

    if "data" not in raw:
        missing.append("data")
        records: list[dict[str, object]] = []
    elif not isinstance(raw["data"], list):
        omitted.add("invalid_records")
        omitted_count += 1
        records = []
    else:
        source_records = raw["data"]
        if len(source_records) > _MAX_ROWS:
            raise RfPlanningHistoryError()
        records = []
        for index, record in enumerate(source_records):
            if not isinstance(record, dict):
                omitted.add("invalid_records")
                omitted_count += 1
                continue
            _check_keys(record)
            projected: dict[str, object] = {}
            for source, (target, kind) in _RECORD_FIELDS.items():
                if source not in record:
                    continue
                value = record[source]
                if _valid(value, kind):
                    projected[target] = value
                else:
                    omitted.add("invalid_record_values")
                    omitted_count += 1
            redacted = sum(1 for key in record if key in _REDACTED_FIELDS)
            redacted_count += redacted
            if history_ref_for_id is not None and "planningHistroyId" in record:
                raw_history_id = record["planningHistroyId"]
                if isinstance(raw_history_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", raw_history_id):
                    history_ref = history_ref_for_id(raw_history_id)
                    if isinstance(history_ref, str) and re.fullmatch(r"[0-9a-f]{24}", history_ref):
                        projected["history_ref"] = history_ref
                    else:
                        omitted.add("invalid_history_reference")
                        omitted_count += 1
                else:
                    omitted.add("invalid_history_id")
                    omitted_count += 1
            elif history_ref_for_id is not None:
                omitted.add("missing_history_id")
                omitted_count += 1
            extras = sum(1 for key in record if key not in _RECORD_FIELDS and key not in _REDACTED_FIELDS)
            if extras:
                omitted.add("unknown_fields")
                omitted_count += extras
            if start_ms is not None and "time_ms" not in projected:
                omitted.add("missing_record_time")
                omitted_count += 1
                continue
            if (start_ms is not None and end_ms is not None and
                    not start_ms <= projected["time_ms"] <= end_ms):
                omitted.add("out_of_window_records")
                omitted_count += 1
                continue
            records.append(projected)
    data["items"] = records
    data["count"] = len(records)
    truncated = total_rows is not None and total_rows > len(records)
    if truncated:
        omitted.add("page_truncated")
    extras = sum(1 for key in raw if key not in {"totalRows", "currentPage", "currentSize", "data"})
    if extras:
        omitted.add("unknown_fields")
        omitted_count += extras
    return {
        "status": "ok",
        "resource": "rf_planning_history",
        "data": data,
        "partial": bool(missing or omitted_count or truncated),
        "missing_fields": missing,
        "omitted_field_count": omitted_count,
        "omitted_fields": sorted(omitted),
        "redacted_field_count": redacted_count,
        "truncated": truncated,
    }
