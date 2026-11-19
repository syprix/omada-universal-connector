"""Summarize evidenced AP uplink segments without exposing raw identities."""
from __future__ import annotations

import re


class SiteApUplinkPathError(ValueError):
    """Input cannot be projected as a bounded selected-AP report."""


_REF = re.compile(r"[0-9a-f]{24}\Z")
_MAX_APS = 16
_DEVICE_STATES = {
    0: "disconnected", 1: "connected", 2: "pending",
    3: "heartbeat_missed", 4: "isolated",
}


def _safe_ref(value: object) -> str | None:
    return value if isinstance(value, str) and _REF.fullmatch(value) else None


def _safe_device_type(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    if not re.fullmatch(r"[A-Za-z0-9 _./+-]+", value):
        return None
    return value


def _source_data(value: object) -> tuple[dict[str, object] | None, bool, bool]:
    if not isinstance(value, dict) or value.get("status") != "ok":
        return None, True, True
    data = value.get("data")
    if not isinstance(data, dict):
        return None, True, True
    return data, False, value.get("partial") is True


def summarize_site_ap_uplink_paths(
    site_ref: str, device_refs: list[str], inventory: list[dict[str, object]],
    wired_sources: dict[str, object], mesh_sources: dict[str, object],
) -> dict[str, object]:
    """Join current inventory, wired uplink, and active mesh parent evidence."""
    if (not isinstance(site_ref, str) or not _REF.fullmatch(site_ref) or
            not isinstance(device_refs, list) or not 1 <= len(device_refs) <= _MAX_APS or
            any(_safe_ref(ref) is None for ref in device_refs) or
            len(set(device_refs)) != len(device_refs) or not isinstance(inventory, list) or
            not isinstance(wired_sources, dict) or not isinstance(mesh_sources, dict)):
        raise SiteApUplinkPathError("site_ap_uplink_path_invalid")

    items_by_ref: dict[str, dict[str, object]] = {}
    for item in inventory:
        if isinstance(item, dict):
            ref = _safe_ref(item.get("device_ref"))
            if ref is not None:
                items_by_ref[ref] = item
    if any(ref not in items_by_ref for ref in device_refs):
        raise SiteApUplinkPathError("device_ref_unknown")

    reports = []
    unavailable_wired = unavailable_mesh = 0
    unknown_path_count = unknown_neighbor_count = 0
    partial_count = 0
    for device_ref in device_refs:
        item = items_by_ref[device_ref]
        wired, wired_unavailable, wired_partial = _source_data(wired_sources.get(device_ref))
        mesh, mesh_unavailable, mesh_partial = _source_data(mesh_sources.get(device_ref))
        unavailable_wired += wired_unavailable
        unavailable_mesh += mesh_unavailable
        if wired_unavailable or mesh_unavailable or wired_partial or mesh_partial:
            partial_count += 1

        model = item.get("model") if isinstance(item.get("model"), str) else None
        firmware = item.get("firmware") if isinstance(item.get("firmware"), str) else None
        state = item.get("state")
        state_label = _DEVICE_STATES.get(state) if type(state) is int else None
        signals: list[str] = []
        if state_label in {"disconnected", "heartbeat_missed", "isolated"}:
            signals.append("device_inventory_reports_" + state_label)

        mesh_linked = mesh.get("wireless_linked") if mesh else None
        mesh_uplink = mesh.get("wireless_uplink") if mesh else None
        if not isinstance(mesh_uplink, dict):
            mesh_uplink = {}
        wired_data = wired.get("wiredUplink") if wired else None
        if not isinstance(wired_data, dict):
            wired_data = {}

        path_kind = "unknown"
        next_hop_ref = None
        next_hop_type = None
        segment_status = "unknown"
        wired_rate = wired_data.get("rate_mbps")
        if mesh_linked is True:
            path_kind = "mesh"
            next_hop_ref = _safe_ref(mesh_uplink.get("uplink_ap_ref"))
            if next_hop_ref is not None:
                segment_status = "mapped"
            else:
                segment_status = "not_in_ap_inventory"
                signals.append("mesh_parent_not_mapped")
        elif type(wired_rate) is int and wired_rate > 0:
            # A successful wired read can establish this segment even when the
            # separate mesh source is unavailable or lacks its Boolean field.
            path_kind = "wired"
            next_hop_ref = _safe_ref(wired_data.get("uplink_device_ref"))
            if next_hop_ref is not None:
                segment_status = "mapped"
            else:
                segment_status = "not_in_device_inventory"
                signals.append("wired_neighbor_not_mapped")
        elif mesh_linked is False and type(wired_rate) is int and wired_rate == 0:
            path_kind = "no_active_link"
            segment_status = "reported_disconnected"
            signals.append("wired_uplink_reports_disconnected")
        elif type(wired_rate) is not int:
            signals.append("wired_link_rate_unknown")
        if type(mesh_linked) is not bool:
            signals.append("wireless_link_state_unknown")

        if path_kind == "unknown":
            unknown_path_count += 1
        if segment_status in {"not_in_ap_inventory", "not_in_device_inventory"}:
            unknown_neighbor_count += 1
        if wired is not None:
            for key in ("upErrorsPackets", "downErrorsPackets"):
                if type(wired_data.get(key)) is int and wired_data[key] > 0:
                    signals.append("reported_uplink_errors_nonzero")
                    break
            for key in ("upDropPackets", "downDropPackets"):
                if type(wired_data.get(key)) is int and wired_data[key] > 0:
                    signals.append("reported_uplink_drops_nonzero")
                    break
        if path_kind == "mesh":
            if type(mesh_uplink.get("rssi")) is int:
                mesh_rssi = mesh_uplink["rssi"]
            else:
                mesh_rssi = None
                signals.append("mesh_rssi_unavailable")
            if type(mesh_uplink.get("snr")) is int:
                mesh_snr = mesh_uplink["snr"]
            else:
                mesh_snr = None
                signals.append("mesh_snr_unavailable")
            mesh_rates = {
                key: mesh_uplink[key] for key in ("tx_rate_mbps", "rx_rate_mbps")
                if type(mesh_uplink.get(key)) is int
            }
        else:
            mesh_rssi = mesh_snr = None
            mesh_rates = {}

        if wired_unavailable:
            signals.append("wired_uplink_unavailable")
        elif wired_partial:
            signals.append("wired_uplink_partial")
        if mesh_unavailable:
            signals.append("mesh_statistics_unavailable")
        elif mesh_partial:
            signals.append("mesh_statistics_partial")
        row: dict[str, object] = {
            "device_ref": device_ref,
            "inventory_state_code": state if type(state) is int else None,
            "inventory_state": state_label or ("unclassified" if type(state) is int else None),
            "path": {
                "link_kind": path_kind,
                "next_hop_ref": next_hop_ref,
                "next_hop_type": _safe_device_type(
                    items_by_ref.get(next_hop_ref, {}).get("device_type")
                    if next_hop_ref else None),
                "segment_status": segment_status,
                "continuation": "not_examined" if next_hop_ref else "unknown",
            },
            "review_signals": sorted(set(signals)),
        }
        if model is not None:
            row["model"] = model
        if firmware is not None:
            row["firmware"] = firmware
        if wired is not None:
            row["wired_link"] = {
                key: wired_data[key] for key in (
                    "rate_mbps", "duplex", "linkStatus", "linkSpeed",
                    "upErrorsPackets", "downErrorsPackets",
                    "upDropPackets", "downDropPackets")
                if key in wired_data
            }
        if mesh is not None:
            row["mesh_link"] = {
                "wireless_linked": mesh_linked,
                "rssi": mesh_rssi, "snr": mesh_snr, **mesh_rates,
                "scan_status": mesh.get("scan_status"),
            }
        reports.append(row)

    selected_ref_set = set(device_refs)
    for row in reports:
        path = row["path"]
        if path["next_hop_ref"] in selected_ref_set:
            path["continuation"] = "selected_device_included"

    partial = bool(partial_count or unavailable_wired or unavailable_mesh or
                   unknown_path_count or unknown_neighbor_count)
    return {
        "status": "ok", "resource": "site_ap_uplink_path_summary",
        "site_ref": site_ref, "selected_ap_count": len(device_refs),
        "aps": reports,
        "source_coverage": {
            "partial_ap_count": partial_count,
            "unavailable_wired_uplink_count": unavailable_wired,
            "unavailable_mesh_statistics_count": unavailable_mesh,
            "unknown_path_count": unknown_path_count,
            "unmapped_next_hop_count": unknown_neighbor_count,
        },
        "partial": partial,
        "connection_cause": "not_inferred",
    }
