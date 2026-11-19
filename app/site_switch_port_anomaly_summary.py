"""Redacted review signals combining the current switch inventory and port feeds."""
from __future__ import annotations

import re
from collections.abc import Mapping

try:
    from .switch_port_counters import SwitchPortCountersError, project_switch_port_counters
except ImportError:  # direct execution in the image
    from switch_port_counters import SwitchPortCountersError, project_switch_port_counters


class SwitchPortAnomalySummaryError(ValueError):
    """The input cannot be safely bounded or joined to the current inventory."""


_REF = re.compile(r"[0-9a-f]{24}\Z")
_MAC = re.compile(r"(?:[0-9A-Fa-f]{2}(?P<sep>[:-])){5}[0-9A-Fa-f]{2}\Z")
_MAX_SWITCHES = 32
_MAX_ROWS = 4096


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


def summarize_site_switch_port_anomalies(
    inventory_items: object,
    switch_macs: object,
    overview_rows: object | None,
    counter_rows: object | None,
    *,
    overview_error: str | None = None,
    counter_error: str | None = None,
) -> dict[str, object]:
    """Join bounded current port state and cumulative error counters by switch ref/port.

    Signals are observations for review. This does not infer a fault, counter rate,
    expected link state, or port-drop count.
    """
    if not isinstance(inventory_items, list) or len(inventory_items) > _MAX_ROWS:
        raise SwitchPortAnomalySummaryError("inventory_invalid")
    if not isinstance(switch_macs, Mapping) or len(switch_macs) > _MAX_ROWS:
        raise SwitchPortAnomalySummaryError("inventory_invalid")
    if overview_rows is not None and (not isinstance(overview_rows, list) or len(overview_rows) > _MAX_ROWS):
        raise SwitchPortAnomalySummaryError("overview_invalid")
    if counter_rows is not None and (not isinstance(counter_rows, list) or len(counter_rows) > _MAX_ROWS):
        raise SwitchPortAnomalySummaryError("counters_invalid")

    switch_items: dict[str, Mapping[str, object]] = {}
    unmapped_inventory_switch_count = 0
    for item in inventory_items:
        if not isinstance(item, Mapping):
            continue
        ref, kind = item.get("device_ref"), item.get("device_type")
        if type(kind) is str and kind.strip().casefold() in {"switch", "sw"}:
            if type(ref) is str and _REF.fullmatch(ref) and ref in switch_macs:
                switch_items[ref] = item
            else:
                unmapped_inventory_switch_count += 1

    ordered_refs = sorted(switch_items)
    selected_refs = ordered_refs[:_MAX_SWITCHES]
    omitted = len(ordered_refs) - len(selected_refs)
    normalized: dict[str, list[str]] = {}
    for ref in selected_refs:
        mac = _mac_key(switch_macs.get(ref))
        if mac is not None:
            normalized.setdefault(mac, []).append(ref)
    mac_to_ref = {mac: refs[0] for mac, refs in normalized.items() if len(refs) == 1}
    ambiguous_refs = {ref for refs in normalized.values() if len(refs) > 1 for ref in refs}

    ports_by_ref: dict[str, dict[int, dict[str, object]]] = {
        ref: {} for ref in selected_refs if ref not in ambiguous_refs
    }
    invalid_overview = duplicate_overview_ports = missing_status_fields = 0
    if overview_rows is not None:
        for row in overview_rows:
            if not isinstance(row, Mapping):
                invalid_overview += 1
                continue
            row_mac = _mac_key(row.get("switchMac"))
            if row_mac is None:
                invalid_overview += 1
                continue
            ref = mac_to_ref.get(row_mac)
            if ref is None:
                # Rows for switches outside the bounded inventory are simply out of scope.
                continue
            port = row.get("port")
            if type(port) is not int or not 0 <= port <= 4096:
                invalid_overview += 1
                continue
            ports = ports_by_ref[ref]
            if port in ports:
                duplicate_overview_ports += 1
                continue
            out: dict[str, object] = {"port": port, "signals": []}
            connected = row.get("connectedStatus")
            if type(connected) is int and -(2**31) <= connected <= 2**31 - 1:
                out["connected_status_code"] = connected
            elif "connectedStatus" in row:
                invalid_overview += 1
            else:
                missing_status_fields += 1
            status = row.get("portStatus")
            if isinstance(status, Mapping):
                link = status.get("linkStatus")
                if type(link) is int and -(2**31) <= link <= 2**31 - 1:
                    out["link_status_code"] = link
                elif "linkStatus" in status:
                    invalid_overview += 1
                else:
                    missing_status_fields += 1
            elif status is not None:
                invalid_overview += 1
            else:
                missing_status_fields += 1
            ports[port] = out

    counter_maps: dict[str, dict[int, dict[str, int]]] = {
        ref: {} for ref in selected_refs if ref not in ambiguous_refs
    }
    counter_partial_refs: set[str] = set()
    counter_duplicates = counter_invalid = 0
    if counter_rows is not None:
        for ref in selected_refs:
            if ref in ambiguous_refs:
                continue
            mac = switch_macs.get(ref)
            try:
                projected = project_switch_port_counters(counter_rows, mac)
            except SwitchPortCountersError:
                counter_partial_refs.add(ref)
                counter_invalid += 1
                continue
            if projected["partial"]:
                counter_partial_refs.add(ref)
            for row in projected["data"]["items"]:
                port = row["port"]
                if port in counter_maps[ref]:
                    counter_duplicates += 1
                    counter_partial_refs.add(ref)
                    continue
                safe_errors = {
                    key: row[key] for key in ("txErrors", "rxErrors")
                    if type(row.get(key)) is int and row[key] >= 0
                }
                counter_maps[ref][port] = safe_errors
                if len(safe_errors) != 2:
                    counter_partial_refs.add(ref)

    result_switches: list[dict[str, object]] = []
    missing_counter_ports = missing_overview_ports = 0
    unjoined_counter_ports = 0
    signal_port_count = 0
    for ref in selected_refs:
        if ref in ambiguous_refs:
            result_switches.append({"switch_ref": ref, "status": "ambiguous_inventory", "ports": []})
            continue
        item = switch_items[ref]
        if not ports_by_ref[ref]:
            missing_overview_ports += 1
        switch_result: dict[str, object] = {"switch_ref": ref, "ports": []}
        if type(item.get("state")) is int:
            switch_result["inventory_state"] = item["state"]
        port_results = []
        for port in sorted(ports_by_ref[ref]):
            current = ports_by_ref[ref][port]
            counter = counter_maps.get(ref, {}).get(port)
            signals: list[str] = current["signals"]
            if counter is None:
                missing_counter_ports += 2
            else:
                for key in ("txErrors", "rxErrors"):
                    if key in counter:
                        current[key] = counter[key]
                        if counter[key] > 0:
                            signals.append("nonzero_" + key)
                    else:
                        missing_counter_ports += 1
            if signals:
                signal_port_count += 1
            current["signals"] = signals
            port_results.append(current)
        unjoined_counter_ports += len(set(counter_maps.get(ref, {})) - set(ports_by_ref[ref]))
        switch_result["ports"] = port_results
        switch_result["port_count"] = len(port_results)
        switch_result["review_signal_count"] = sum(bool(row["signals"]) for row in port_results)
        if ref in counter_partial_refs:
            switch_result["counter_coverage"] = "partial"
        elif counter_error:
            switch_result["counter_coverage"] = "unavailable"
        else:
            switch_result["counter_coverage"] = "available_for_observed_rows"
        result_switches.append(switch_result)

    partial = bool(
        omitted or unmapped_inventory_switch_count or ambiguous_refs or invalid_overview or duplicate_overview_ports or
        missing_status_fields or
        counter_duplicates or counter_invalid or missing_counter_ports or
        missing_overview_ports or unjoined_counter_ports or overview_rows is None or counter_rows is None or
        overview_error or counter_error
    )
    return {
        "status": "ok",
        "resource": "site_switch_port_anomaly_summary",
        "interpretation": "review_signals_not_diagnoses",
        "switch_limit": _MAX_SWITCHES,
        "source_contract": "port_status_and_error_fields_are_fully_described_only_in_ER7212PC_export",
        "live_support": "unknown",
        "switches_scanned": len(selected_refs),
        "switches_omitted_device_limit": omitted,
        "switches_missing_inventory_mac": unmapped_inventory_switch_count,
        "ambiguous_switch_count": len(ambiguous_refs),
        "review_signal_port_count": signal_port_count,
        "drop_counters": "not_available_in_documented_port_counter_response",
        "counter_interval": "one_cumulative_counter_read; no rate or trend calculated",
        "temporal_alignment": "inventory_and_port_feeds_are_separate_sequential_reads",
        "source_errors": {
            key: value for key, value in (
                ("port_overview", overview_error), ("port_counters", counter_error)
            ) if value is not None
        },
        "data": {"switches": result_switches},
        "partial": partial,
        "coverage": {
            "invalid_overview_rows": invalid_overview,
            "duplicate_overview_ports": duplicate_overview_ports,
            "missing_status_fields": missing_status_fields,
            "duplicate_counter_ports": counter_duplicates,
            "invalid_counter_switch_rows": counter_invalid,
            "counter_switches_partial": len(counter_partial_refs),
            "missing_error_counter_fields": missing_counter_ports,
            "ports_without_overview": missing_overview_ports,
            "counter_ports_without_overview": unjoined_counter_ports,
        },
    }
