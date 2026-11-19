from __future__ import annotations

from typing import Any


MAX_BACKUP_FILES = 512
_FILE_FIELDS = {"fileName", "backupTime", "size"}


class ControllerBackupInventoryError(ValueError):
    """Raised when the documented backup inventory response is not bounded."""


def project_controller_backup_inventory(
    file_result: Any,
    schedule_result: dict[str, object],
    status_result: dict[str, object],
    *,
    source_scope: str = "controller_file_list_response",
) -> dict[str, object]:
    if not isinstance(file_result, dict) or len(file_result) > 16:
        raise ControllerBackupInventoryError("response_invalid")

    raw_files = file_result.get("fileList")
    if not isinstance(raw_files, list):
        raise ControllerBackupInventoryError("response_invalid")

    omitted = max(0, len(raw_files) - MAX_BACKUP_FILES)
    rows = raw_files[:MAX_BACKUP_FILES]
    partial = bool(omitted)
    unknown_fields = len(set(file_result) - {"fileList"})
    invalid_entries = 0
    backup_times: list[int] = []
    total_size = 0
    size_count = 0

    for row in rows:
        if not isinstance(row, dict) or len(row) > 12:
            invalid_entries += 1
            partial = True
            continue
        unknown_fields += len(set(row) - _FILE_FIELDS)
        raw_time = row.get("backupTime")
        raw_size = row.get("size")
        if type(raw_time) is int and 0 <= raw_time <= 9_999_999_999_999:
            backup_times.append(raw_time)
        else:
            invalid_entries += 1
            partial = True
        if type(raw_size) is int and 0 <= raw_size <= 2**63 - 1:
            total_size += raw_size
            size_count += 1
        else:
            invalid_entries += 1
            partial = True
    if unknown_fields:
        partial = True
    if size_count != len(rows) - sum(
            not isinstance(row, dict) or len(row) > 12 for row in rows):
        partial = True

    schedule_data = schedule_result.get("data")
    if not isinstance(schedule_data, dict):
        schedule_data = {}
        partial = True
    schedule = {
        key: schedule_data[key]
        for key in ("enabled", "schedule_configured", "retention_days",
                    "maximum_files", "storage_type")
        if key in schedule_data
    }
    if schedule_result.get("partial") is True:
        partial = True

    status_data = status_result.get("data")
    backup_status = status_data.get("status") if isinstance(status_data, dict) else None
    if backup_status not in {"idle_or_finished", "running"}:
        partial = True
        backup_status = None
    if status_result.get("partial") is True:
        partial = True

    return {
        "status": "partial" if partial else "ok",
        "partial": partial,
        "backup_file_count": len(rows),
        "omitted_backup_file_count": omitted,
        "latest_listed_backup_time_ms": max(backup_times) if backup_times else None,
        "total_listed_backup_bytes": total_size if size_count else None,
        "backup_activity": backup_status,
        "schedule": schedule,
        "invalid_entry_count": invalid_entries,
        "unknown_field_count": unknown_fields,
        "source_scope": source_scope,
    }
