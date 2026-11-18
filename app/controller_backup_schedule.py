"""Redacted summary for the documented controller backup schedule read."""
from __future__ import annotations

from typing import Any

_FIELDS = {
    "enable", "occurrence", "maxNumberOfFile", "retention", "savingPath",
    "availablePaths", "fileServerConfig", "storageType", "dataSheets",
    "retainSetting", "retainUser", "retainAuthRecord", "retainFirmwareLog",
}
_RETENTION = {-1, 0, 7, 30, 60, 90, 180, 365}


class ControllerBackupScheduleError(ValueError):
    """Raised when the backup schedule payload is not safely understood."""


def project_controller_backup_schedule(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 32:
        raise ControllerBackupScheduleError("response_invalid")

    data: dict[str, object] = {}
    invalid = 0
    missing = 0
    unknown = len(set(result) - _FIELDS)

    enabled = result.get("enable")
    if isinstance(enabled, bool):
        data["enabled"] = enabled
    elif "enable" in result:
        invalid += 1
    else:
        missing += 1

    retention = result.get("retention")
    if retention is not None:
        if type(retention) is int and retention in _RETENTION:
            data["retention_days"] = retention
        else:
            invalid += 1

    max_files = result.get("maxNumberOfFile")
    if max_files is not None:
        if type(max_files) is int and 0 <= max_files <= 10000:
            data["maximum_files"] = max_files
        else:
            invalid += 1

    storage_type = result.get("storageType")
    if storage_type is not None:
        if type(storage_type) is int and storage_type in {0, 1, 2}:
            data["storage_type"] = {0: "file_server", 1: "cloud", 2: "local_disk"}[storage_type]
        else:
            invalid += 1

    for source, target in (("occurrence", "schedule_configured"),
                           ("fileServerConfig", "file_server_configured")):
        if source in result:
            value = result[source]
            if isinstance(value, dict) and len(value) <= 32:
                data[target] = bool(value)
                if source == "fileServerConfig":
                    unknown += len(value)
            elif value is None:
                data[target] = False
            else:
                invalid += 1

    for source in ("savingPath", "availablePaths"):
        if source in result:
            value = result[source]
            if source == "savingPath":
                if isinstance(value, str) and len(value) <= 2048:
                    data["saving_path_configured"] = bool(value)
                elif value is not None:
                    invalid += 1
            elif isinstance(value, list) and len(value) <= 64 and all(
                    isinstance(x, str) and len(x) <= 2048 for x in value):
                data["available_path_count"] = len(value)
            else:
                invalid += 1

    sheets = result.get("dataSheets")
    if sheets is not None:
        if isinstance(sheets, list) and len(sheets) <= 64 and all(
                isinstance(x, str) and len(x) <= 64 for x in sheets):
            data["data_sheet_count"] = len(sheets)
        else:
            invalid += 1

    retention_flags = ("retainSetting", "retainUser", "retainAuthRecord", "retainFirmwareLog")
    valid_flags = 0
    for field in retention_flags:
        if field in result:
            if isinstance(result[field], bool):
                valid_flags += 1
            else:
                invalid += 1
    if valid_flags:
        data["retention_flag_count"] = valid_flags

    return {
        "data": data,
        "missing_field_count": missing,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(missing or invalid or unknown),
    }
