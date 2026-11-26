"""Redacted PoE budget, port and schedule view for one site."""
from __future__ import annotations

import re
from collections.abc import Mapping

try:
    from .switch_port_poe_info import SwitchPortPoeInfoError, project_switch_port_poe_info
except ImportError:  # direct execution in the image
    from switch_port_poe_info import SwitchPortPoeInfoError, project_switch_port_poe_info


class SitePoeScheduleSummaryError(ValueError):
    """The supplied inventory or source feeds cannot be safely bounded."""


_REF = re.compile(r"[0-9a-f]{24}\Z")
_MAC = re.compile(r"(?:[0-9A-Fa-f]{2}(?P<sep>[:-])){5}[0-9A-Fa-f]{2}\Z")
_MAX_SWITCHES = 32
_MAX_ROWS = 4096
_MAX_PORTS = 4096
_INT32_MAX = 2**31 - 1


def _mac_key(value: object) -> str | None:
    if type(value) is not str:
        return None
    match = _MAC.fullmatch(value)
    if match is None:
        return None
    sep = match.group("sep")
    if any(value[i] != sep for i in (2, 5, 8, 11, 14)):
        return None
    return value.replace(sep, "").lower()


def _rows(value: object | None, label: str) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_ROWS:
        raise SitePoeScheduleSummaryError(label + "_invalid")
    return value


def _count_by_value(target: dict[str, int], value: object) -> None:
    key = str(value)
    target[key] = target.get(key, 0) + 1


def summarize_site_poe_schedule(
    inventory_items: object,
    switch_macs: object,
    poe_port_rows: object | None,
    usage_rows: object | None,
    port_info_rows: object | None,
    schedule_rows: object | None,
    time_range_rows: object | None,
    *,
    source_errors: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Join current PoE records only where device, unit and time-range evidence aligns."""
    if not isinstance(inventory_items, list) or len(inventory_items) > _MAX_ROWS:
        raise SitePoeScheduleSummaryError("inventory_invalid")
    if not isinstance(switch_macs, Mapping) or len(switch_macs) > _MAX_ROWS:
        raise SitePoeScheduleSummaryError("inventory_invalid")
    poe_ports = _rows(poe_port_rows, "poe_port_inventory")
    usage = _rows(usage_rows, "poe_usage")
    port_info = _rows(port_info_rows, "poe_port_info")
    schedules = _rows(schedule_rows, "poe_schedules")
    time_ranges = _rows(time_range_rows, "time_range_profiles")
    errors = dict(source_errors or {})

    inventory_by_ref: dict[str, Mapping[str, object]] = {}
    for item in inventory_items:
        if not isinstance(item, Mapping):
            continue
        ref, kind = item.get("device_ref"), item.get("device_type")
        if (type(ref) is str and _REF.fullmatch(ref) and type(kind) is str and
                kind.strip().casefold() in {"switch", "sw"} and ref in switch_macs):
            inventory_by_ref[ref] = item
    ordered_refs = sorted(inventory_by_ref)
    selected_refs = ordered_refs[:_MAX_SWITCHES]
    omitted = len(ordered_refs) - len(selected_refs)
    mac_refs: dict[str, list[str]] = {}
    for ref in selected_refs:
        mac = _mac_key(switch_macs.get(ref))
        if mac is not None:
            mac_refs.setdefault(mac, []).append(ref)
    unique_mac_refs = {mac: refs[0] for mac, refs in mac_refs.items() if len(refs) == 1}
    ambiguous = {ref for refs in mac_refs.values() if len(refs) > 1 for ref in refs}
    result_by_ref: dict[str, dict[str, object]] = {}
    for ref in selected_refs:
        if ref in ambiguous:
            result_by_ref[ref] = {"switch_ref": ref, "status": "ambiguous_inventory"}
            continue
        result_by_ref[ref] = {
            "switch_ref": ref,
            "poe_capable_ports": [],
            "port_telemetry": {},
            "schedules": [],
        }

    partial = bool(omitted or ambiguous or errors)
    invalid_port_inventory = invalid_usage = invalid_schedule = 0
    duplicate_usage = schedules_without_targets = unresolved_schedule_targets = 0
    missing_usage = missing_port_info = missing_range_links = 0

    seen_capability_rows: set[str] = set()
    for row in poe_ports:
        if not isinstance(row, Mapping):
            invalid_port_inventory += 1
            continue
        mac = _mac_key(row.get("mac"))
        ref = unique_mac_refs.get(mac or "")
        if ref is None:
            if mac is None:
                invalid_port_inventory += 1
            continue
        details = row.get("poePort")
        ids = details.get("poePortIds") if isinstance(details, Mapping) else None
        if not isinstance(ids, list) or len(ids) > _MAX_PORTS:
            invalid_port_inventory += 1
            continue
        seen_capability_rows.add(ref)
        valid: set[int] = set()
        for port in ids:
            if type(port) is int and 0 <= port <= _MAX_PORTS:
                valid.add(port)
            else:
                invalid_port_inventory += 1
        result_by_ref[ref]["poe_capable_ports"] = sorted(valid)

    budget_seen: set[str] = set()
    for row in usage:
        if not isinstance(row, Mapping):
            invalid_usage += 1
            continue
        mac = _mac_key(row.get("mac"))
        ref = unique_mac_refs.get(mac or "")
        if ref is None:
            if mac is None:
                invalid_usage += 1
            continue
        if ref in budget_seen:
            duplicate_usage += 1
            continue
        budget_seen.add(ref)
        used, capacity = row.get("totalPowerUsed"), row.get("totalPower")
        if (type(used) is not int or type(capacity) is not int or
                not 0 <= used <= _INT32_MAX or not 0 <= capacity <= _INT32_MAX):
            invalid_usage += 1
            continue
        budget: dict[str, int] = {
            "used_watts": used,
            "rated_capacity_watts": capacity,
            "available_watts": capacity - used,
        }
        if used > capacity:
            budget["over_capacity_watts"] = used - capacity
        result_by_ref[ref]["power_budget"] = budget

    if port_info_rows is not None:
        for ref in selected_refs:
            if ref in ambiguous:
                continue
            try:
                projected = project_switch_port_poe_info(port_info_rows, switch_macs.get(ref))
            except SwitchPortPoeInfoError:
                missing_port_info += 1
                continue
            data = projected.get("data", {})
            items = data.get("items", [])
            telemetry: dict[str, object] = {
                "reported_port_count": len(items),
                "support_poe_true_count": 0,
                "poe_display_type_counts": {},
                "poe_value_counts": {},
                "poe_status_value_counts": {},
                "measurement_presence_counts": {"power": 0, "voltage": 0, "current": 0},
            }
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                if item.get("supportPoe") is True:
                    telemetry["support_poe_true_count"] += 1
                for field, output_key in (("poeDisplayType", "poe_display_type_counts"),
                                          ("poe", "poe_value_counts"),
                                          ("poeStatus", "poe_status_value_counts")):
                    if field in item:
                        _count_by_value(telemetry[output_key], item[field])
                for field in ("power", "voltage", "current"):
                    if field in item:
                        telemetry["measurement_presence_counts"][field] += 1
            result_by_ref[ref]["port_telemetry"] = telemetry
            if projected.get("partial") or not projected.get("target_rows_present"):
                missing_port_info += 1

    profile_counts: dict[str, int] = {}
    duplicate_profile_ids = 0
    for profile in time_ranges:
        if not isinstance(profile, Mapping):
            missing_range_links += 1
            continue
        profile_id = profile.get("profileId")
        if type(profile_id) is not str or not profile_id:
            missing_range_links += 1
        else:
            profile_counts[profile_id] = profile_counts.get(profile_id, 0) + 1
            if profile_counts[profile_id] > 1:
                duplicate_profile_ids += 1

    for row in schedules:
        if not isinstance(row, Mapping):
            invalid_schedule += 1
            continue
        status = row.get("status")
        turn_on_time = row.get("turnOnTime")
        target_map = row.get("poePortsMap")
        next_execute = row.get("nextExecute")
        if type(status) is not bool or type(turn_on_time) is not str or not isinstance(target_map, Mapping):
            invalid_schedule += 1
            continue
        time_range_resolved = profile_counts.get(turn_on_time) == 1
        if not time_range_resolved:
            missing_range_links += 1
        matched_targets = 0
        for mac_value, values in target_map.items():
            mac = _mac_key(mac_value)
            ref = unique_mac_refs.get(mac or "")
            if ref is None:
                unresolved_schedule_targets += 1
                if mac is None:
                    invalid_schedule += 1
                continue
            if not isinstance(values, list) or len(values) > _MAX_PORTS:
                invalid_schedule += 1
                continue
            ports = sorted({p for p in values if type(p) is int and 0 <= p <= _MAX_PORTS})
            invalid_schedule += sum(1 for p in values if type(p) is not int or not 0 <= p <= _MAX_PORTS)
            result_by_ref[ref]["schedules"].append({
                "enabled": status,
                "scheduled_ports": ports,
                "time_range_resolved": time_range_resolved,
                "next_execute_present": type(next_execute) is int,
            })
            matched_targets += 1
        if matched_targets == 0:
            schedules_without_targets += 1

    for ref in selected_refs:
        if ref in ambiguous:
            continue
        if ref not in budget_seen:
            missing_usage += 1
        if poe_port_rows is not None and ref not in seen_capability_rows:
            invalid_port_inventory += 1

    partial = bool(partial or invalid_port_inventory or invalid_usage or invalid_schedule or
                   duplicate_usage or schedules_without_targets or unresolved_schedule_targets or missing_usage or
                   missing_port_info or missing_range_links or duplicate_profile_ids or
                   poe_port_rows is None or usage_rows is None or port_info_rows is None or
                   schedule_rows is None or time_range_rows is None)
    for ref, item in result_by_ref.items():
        item["poe_capable_port_count"] = len(item.get("poe_capable_ports", []))
        item["schedule_count"] = len(item.get("schedules", []))

    return {
        "status": "partial" if partial else "ok",
        "resource": "site_poe_schedule_summary",
        "switch_limit": _MAX_SWITCHES,
        "switches_scanned": len(selected_refs),
        "switches_omitted_device_limit": omitted,
        "ambiguous_switch_count": len(ambiguous),
        "source_contract": "detailed_feed_fields_documented_in_all_three_exports; descriptions_and_numeric_wrappers_vary",
        "live_support": "unknown",
        "power_budget_units": "watts_documented_for_used_and_capacity_values_only",
        "port_measurement_units": "unspecified; values are not compared with rated capacity",
        "schedule_time_resolution": "profile_id_match_only; schedule names_and_profile_details_omitted",
        "next_execute": "presence_only; source timestamp unit is unspecified",
        "source_errors": errors,
        "data": {"switches": [result_by_ref[ref] for ref in selected_refs]},
        "partial": partial,
        "coverage": {
            "invalid_poe_port_rows": invalid_port_inventory,
            "invalid_power_usage_rows": invalid_usage,
            "duplicate_power_usage_rows": duplicate_usage,
            "switches_missing_power_usage": missing_usage,
            "switches_missing_or_partial_port_info": missing_port_info,
            "invalid_schedule_rows_or_ports": invalid_schedule,
            "schedules_without_mapped_switch_targets": schedules_without_targets,
            "unresolved_schedule_targets": unresolved_schedule_targets,
            "unresolved_time_range_links": missing_range_links,
            "duplicate_time_range_profile_ids": duplicate_profile_ids,
        },
    }
