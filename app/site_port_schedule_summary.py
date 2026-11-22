"""Redacted page counts for switch port schedules and supported ports."""
from __future__ import annotations

from typing import Any


class SitePortScheduleError(ValueError):
    """Malformed schedule or supported-port response."""


_MAX_PAGE = 10_000
_MAX_PAGE_SIZE = 100
_INT64_MAX = (1 << 63) - 1


def project_site_port_schedule_summary(schedule_result: Any, supported_result: Any,
                                        page_number: int, page_size: int) -> dict[str, object]:
    if (type(page_number) is not int or not 0 <= page_number <= _MAX_PAGE or
            type(page_size) is not int or not 1 <= page_size <= _MAX_PAGE_SIZE):
        raise SitePortScheduleError("request_invalid")
    if not isinstance(schedule_result, dict) or len(schedule_result) > 8:
        raise SitePortScheduleError("schedule_page_invalid")
    rows = schedule_result.get("data")
    total, current, current_size = (schedule_result.get(k)
                                    for k in ("totalRows", "currentPage", "currentSize"))
    source_page = page_number + 1
    if (not isinstance(rows, list) or len(rows) > page_size or
            type(total) is not int or total < 0 or type(current) is not int or
            current != source_page or type(current_size) is not int or
            not len(rows) <= current_size <= page_size):
        raise SitePortScheduleError("schedule_page_invalid")
    if not isinstance(supported_result, list) or len(supported_result) > 10_000:
        raise SitePortScheduleError("supported_ports_invalid")

    supported: dict[str, set[int]] = {}
    all_device_refs: set[str] = set()
    ambiguous_refs: set[str] = set()
    duplicate_device_refs = devices_without_port_list = invalid = unknown = 0
    for device in supported_result:
        if not isinstance(device, dict) or len(device) > 16:
            invalid += 1
            continue
        mac = device.get("mac")
        ports = device.get("ports")
        if not isinstance(mac, str) or not mac or len(mac) > 128:
            invalid += 1
            continue
        all_device_refs.add(mac)
        unknown += len(set(device) - {"type", "mac", "name", "site", "model",
                                      "modelVersion", "hwVersion", "status", "sn", "ports"})
        if mac in ambiguous_refs:
            continue
        if mac in supported:
            duplicate_device_refs += 1
            ambiguous_refs.add(mac)
            supported.pop(mac, None)
            continue
        if not isinstance(ports, dict) or len(ports) > 8:
            devices_without_port_list += 1
            continue
        unknown += len(set(ports) - {"portNum", "portIds"})
        port_ids = ports.get("portIds")
        port_num = ports.get("portNum")
        if (not isinstance(port_ids, list) or len(port_ids) > 4096 or
                type(port_num) is not int or not 0 <= port_num <= (1 << 31) - 1):
            invalid += 1
            continue
        if any(type(port_id) is not int or not 0 <= port_id <= (1 << 31) - 1
               for port_id in port_ids):
            invalid += 1
            continue
        supported[mac] = set(port_ids)

    enabled = disabled = unknown_status = 0
    time_ref_present = time_ref_missing = next_execute_present = next_execute_missing = 0
    dst_true = dst_false = dst_missing = 0
    schedule_port_memberships = supported_memberships = unsupported_memberships = 0
    unmatched_device_refs = ambiguous_device_refs = missing_port_details = 0
    for schedule in rows:
        if not isinstance(schedule, dict) or len(schedule) > 20:
            invalid += 1
            continue
        unknown += len(set(schedule) - {"id", "siteId", "name", "status", "turnOnTime",
                                        "portsMap", "nextExecute", "notInDst"})
        status = schedule.get("status")
        if type(status) is bool:
            enabled += int(status)
            disabled += int(not status)
        else:
            unknown_status += 1
        time_ref = schedule.get("turnOnTime")
        if isinstance(time_ref, str) and time_ref:
            time_ref_present += 1
        else:
            time_ref_missing += 1
        if "nextExecute" in schedule:
            value = schedule["nextExecute"]
            if type(value) is int and 0 <= value <= _INT64_MAX:
                next_execute_present += 1
            else:
                invalid += 1
        else:
            next_execute_missing += 1
        if type(schedule.get("notInDst")) is bool:
            dst_true += int(schedule["notInDst"])
            dst_false += int(not schedule["notInDst"])
        else:
            dst_missing += 1
        port_map = schedule.get("portsMap")
        if not isinstance(port_map, dict) or len(port_map) > 4096:
            invalid += 1
            continue
        for device_mac, port_ids in port_map.items():
            if (not isinstance(device_mac, str) or not device_mac or len(device_mac) > 128 or
                    not isinstance(port_ids, list) or len(port_ids) > 4096):
                invalid += 1
                continue
            if any(type(port_id) is not int or not 0 <= port_id <= (1 << 31) - 1
                   for port_id in port_ids):
                invalid += 1
                continue
            schedule_port_memberships += len(port_ids)
            if device_mac not in supported:
                if device_mac in ambiguous_refs:
                    ambiguous_device_refs += 1
                elif device_mac not in all_device_refs:
                    unmatched_device_refs += 1
                else:
                    missing_port_details += 1
                continue
            supported_ids = supported[device_mac]
            for port_id in port_ids:
                if port_id in supported_ids:
                    supported_memberships += 1
                else:
                    unsupported_memberships += 1
                    missing_port_details += 1

    has_more = total > page_number * page_size + len(rows)
    return {
        "page_number": page_number,
        "page_size": page_size,
        "reported_schedule_count": total,
        "sampled_schedule_count": len(rows),
        "has_more": has_more,
        "enabled_schedule_count": enabled,
        "disabled_schedule_count": disabled,
        "unknown_schedule_status_count": unknown_status,
        "time_range_reference_present_count": time_ref_present,
        "time_range_reference_missing_count": time_ref_missing,
        "next_execution_value_present_count": next_execute_present,
        "next_execution_value_missing_count": next_execute_missing,
        "not_in_dst_true_count": dst_true,
        "not_in_dst_false_count": dst_false,
        "not_in_dst_missing_count": dst_missing,
        "schedule_port_membership_count": schedule_port_memberships,
        "membership_on_documented_supported_ports": supported_memberships,
        "membership_not_listed_as_supported": unsupported_memberships,
        "unmatched_device_reference_count": unmatched_device_refs,
        "ambiguous_device_reference_count": ambiguous_device_refs,
        "devices_without_supported_port_details": devices_without_port_list,
        "invalid_field_count": invalid,
        "unknown_field_count": unknown,
        "partial": bool(has_more or invalid or unknown or unknown_status or dst_missing or
                         unmatched_device_refs or ambiguous_device_refs or
                         devices_without_port_list or missing_port_details),
        "next_execute_unit_interpreted": False,
        "schedule_effect_or_execution_inferred": False,
    }
