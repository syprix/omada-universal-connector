from __future__ import annotations

from typing import Any


class SiteRebootScheduleError(ValueError):
    """Raised when a reboot schedule payload is outside its documented shape."""


MAX_SCHEDULES = 64
MAX_TARGETS = 128
SCHEDULE_COLUMNS = [
    "enabled",
    "recurrence",
    "hour",
    "minute",
    "day_of_week_or_month_day",
    "target_count",
    "target_device_refs",
    "unresolved_target_count",
    "next_execution_time_ms",
]


def _mac_key(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 32:
        return None
    value = value.replace(":", "").replace("-", "").casefold()
    if len(value) != 12 or any(ch not in "0123456789abcdef" for ch in value):
        return None
    return value


def summarize_site_reboot_schedules(
    result: Any,
    inventory_macs_by_ref: dict[str, str],
) -> dict[str, object]:
    if not isinstance(result, list):
        raise SiteRebootScheduleError("response_invalid")

    refs_by_mac: dict[str, list[str]] = {}
    for ref, mac in inventory_macs_by_ref.items():
        key = _mac_key(mac)
        if key:
            refs_by_mac.setdefault(key, []).append(ref)

    rows = result[:MAX_SCHEDULES]
    partial = len(result) > MAX_SCHEDULES
    omitted = max(0, len(result) - MAX_SCHEDULES)
    invalid = 0
    schedules: list[list[object]] = []
    enabled_count = 0
    for row in rows:
        if not isinstance(row, dict) or len(row) > 32:
            invalid += 1
            partial = True
            continue
        if set(row) - {"id", "name", "status", "deviceMacs", "time", "nextExecute"}:
            invalid += 1
            partial = True

        enabled: bool | None = None
        status = row.get("status")
        if isinstance(status, bool):
            enabled = status
            enabled_count += status
        else:
            invalid += 1
            partial = True

        recurrence: str | None = None
        hour: int | None = None
        minute: int | None = None
        day: int | None = None
        raw_time = row.get("time")
        if not isinstance(raw_time, dict) or len(raw_time) > 16:
            invalid += 1
            partial = True
        else:
            if set(raw_time) - {"timingType", "dayOfWeek", "dayOfMonth", "hour", "minute"}:
                invalid += 1
                partial = True
            recurrence_code = raw_time.get("timingType")
            if type(recurrence_code) is int and recurrence_code in {1, 2, 3}:
                recurrence = {1: "daily", 2: "weekly", 3: "monthly"}[recurrence_code]
            else:
                invalid += 1
                partial = True
            raw_hour, raw_minute = raw_time.get("hour"), raw_time.get("minute")
            if type(raw_hour) is int and 0 <= raw_hour <= 23:
                hour = raw_hour
            else:
                invalid += 1
                partial = True
            if type(raw_minute) is int and 0 <= raw_minute <= 59:
                minute = raw_minute
            else:
                invalid += 1
                partial = True
            if recurrence_code == 2:
                raw_day = raw_time.get("dayOfWeek")
                if type(raw_day) is int and 0 <= raw_day <= 6:
                    day = raw_day
                else:
                    invalid += 1
                    partial = True
            elif recurrence_code == 3:
                raw_day = raw_time.get("dayOfMonth")
                if type(raw_day) is int and 1 <= raw_day <= 31:
                    day = raw_day
                else:
                    invalid += 1
                    partial = True

        target_count: int | None = None
        mapped: list[str] = []
        unresolved = 0
        targets = row.get("deviceMacs")
        if isinstance(targets, list) and len(targets) <= MAX_TARGETS:
            target_count = len(targets)
            for mac in targets:
                key = _mac_key(mac)
                refs = refs_by_mac.get(key, []) if key else []
                if len(refs) == 1:
                    mapped.append(refs[0])
                else:
                    unresolved += 1
            if unresolved:
                partial = True
        else:
            target_count = len(targets) if isinstance(targets, list) else None
            unresolved = len(targets) if isinstance(targets, list) else 0
            invalid += 1
            partial = True

        next_execute: int | None = None
        raw_next_execute = row.get("nextExecute")
        if raw_next_execute is not None:
            if type(raw_next_execute) is int and 0 <= raw_next_execute <= 9_999_999_999_999:
                next_execute = raw_next_execute
            else:
                invalid += 1
                partial = True

        schedules.append([
            enabled, recurrence, hour, minute, day, target_count,
            sorted(set(mapped)), unresolved, next_execute,
        ])

    return {
        "status": "partial" if partial else "ok",
        "partial": partial,
        "schedule_count": len(schedules),
        "enabled_count": enabled_count,
        "schedule_columns": SCHEDULE_COLUMNS,
        "schedule_rows": schedules,
        "schedule_clock_timezone": "not_specified_by_source",
        "omitted_schedule_count": omitted,
        "invalid_entry_or_field_count": invalid,
        "schedule_semantics": "configured_schedule_only; does_not_confirm_a_reboot",
    }
