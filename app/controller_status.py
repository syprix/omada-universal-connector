"""Redacted projection for controller status and capacity information."""
from __future__ import annotations

import math
import string
from typing import Any

MAX_SOURCE_FIELDS = 20
MAX_TEXT_LENGTH = 128
MAX_DISKS = 16
MAX_DISK_FIELDS = 4
MAX_CAPACITY_FIELDS = 6
TEXT_FIELDS = {
    "controllerVersion": "controller_version",
    "model": "model",
    "firmwareVersion": "firmware_version",
}
PRESENCE_FIELDS = {"name", "macAddress", "timeZone", "sn", "areaInfo", "informUrl"}
CATEGORY_VALUES = {"localPro", "local", "advanced", "pro"}
CONTROLLER_TYPES = {0, 1, 10, 11, 12, 13, 20}
CAPACITY_FIELDS = {
    "adoptedApNum": "adopted_ap_count", "apCapacity": "ap_capacity",
    "adoptedOswNum": "adopted_switch_count", "oswCapacity": "switch_capacity",
    "adoptedOsgNum": "adopted_gateway_count", "osgCapacity": "gateway_capacity",
}
KNOWN_FIELDS = (set(TEXT_FIELDS) | PRESENCE_FIELDS | {
    "systemTime", "upTime", "category", "controllerType", "hwcStorage", "deviceCapacity",
})


class ControllerStatusError(ValueError):
    """Raised when the controller status response exceeds safe bounds."""


def _safe_text(value: Any, maximum: int = MAX_TEXT_LENGTH) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= maximum and
            all(char in string.printable and char not in "\r\n\t\x0b\x0c" for char in value))


def _storage(rows: Any) -> tuple[dict[str, object], int, int, bool]:
    if not isinstance(rows, list) or len(rows) > MAX_DISKS:
        raise ControllerStatusError("response_invalid")
    disk_count = oc_disk_count = invalid = unknown = 0
    total = used = 0.0
    totals_complete = True
    for row in rows:
        if not isinstance(row, dict) or len(row) > MAX_DISK_FIELDS:
            raise ControllerStatusError("response_invalid")
        disk_count += 1
        unknown += len(set(row) - {"name", "totalStorage", "usedStorage", "ocStorage"})
        if "ocStorage" in row:
            if type(row["ocStorage"]) is bool:
                oc_disk_count += int(row["ocStorage"])
            else:
                invalid += 1
        for source, target in (("totalStorage", "total"), ("usedStorage", "used")):
            if source not in row:
                totals_complete = False
                continue
            value = row[source]
            if (type(value) not in (int, float) or value < 0 or value > 1e15 or
                    not math.isfinite(value)):
                invalid += 1
                totals_complete = False
            elif target == "total":
                total += float(value)
            else:
                used += float(value)
        if "name" in row and not _safe_text(row["name"], 128):
            invalid += 1
    storage: dict[str, object] = {"disk_count": disk_count, "oc_storage_disk_count": oc_disk_count}
    if totals_complete:
        storage["total_storage"] = total
        storage["used_storage"] = used
    return storage, invalid, unknown, totals_complete


def project_controller_status(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > MAX_SOURCE_FIELDS:
        raise ControllerStatusError("response_invalid")
    status: dict[str, object] = {}
    presence: dict[str, bool] = {}
    capacity: dict[str, int] = {}
    invalid = unknown = 0
    for source, target in TEXT_FIELDS.items():
        if source not in result:
            continue
        value = result[source]
        if _safe_text(value):
            status[target] = value
        else:
            invalid += 1
    if "category" in result:
        value = result["category"]
        if isinstance(value, str) and value in CATEGORY_VALUES:
            status["category"] = value
        else:
            invalid += 1
    for source in PRESENCE_FIELDS:
        if source not in result:
            continue
        if _safe_text(result[source]):
            presence[source] = True
        else:
            invalid += 1
    for source, target in (("systemTime", "system_time"), ("upTime", "uptime_seconds")):
        if source not in result:
            continue
        value = result[source]
        if type(value) is int and 0 <= value <= 2**63 - 1:
            status[target] = value
        else:
            invalid += 1
    if "controllerType" in result:
        value = result["controllerType"]
        if type(value) is int and value in CONTROLLER_TYPES:
            status["controller_type"] = value
        else:
            invalid += 1
    if "hwcStorage" in result:
        storage, bad, extra, _ = _storage(result["hwcStorage"])
        status["storage"] = storage
        invalid += bad
        unknown += extra
    if "deviceCapacity" in result:
        raw_capacity = result["deviceCapacity"]
        if not isinstance(raw_capacity, dict) or len(raw_capacity) > MAX_CAPACITY_FIELDS:
            raise ControllerStatusError("response_invalid")
        for source, target in CAPACITY_FIELDS.items():
            if source not in raw_capacity:
                continue
            value = raw_capacity[source]
            if type(value) is int and 0 <= value <= 2**31 - 1:
                capacity[target] = value
            else:
                invalid += 1
        status["capacity"] = capacity
        unknown += len(set(raw_capacity) - set(CAPACITY_FIELDS))
    unknown += len(set(result) - KNOWN_FIELDS)
    missing = len(KNOWN_FIELDS - result.keys())
    if isinstance(result.get("deviceCapacity"), dict):
        missing += len(CAPACITY_FIELDS - result["deviceCapacity"].keys())
    if isinstance(result.get("hwcStorage"), list):
        missing += sum(2 - int("totalStorage" in row) - int("usedStorage" in row)
                       for row in result["hwcStorage"] if isinstance(row, dict))
    data = {
        "status": status,
        "presence": presence,
        "present_count": sum((len(status), len(presence))),
        "missing_count": missing,
        "invalid_count": invalid,
        "unknown_field_count": unknown,
    }
    return {"data": data, "partial": bool(missing or invalid or unknown)}
